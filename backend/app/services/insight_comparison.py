import json
from collections import Counter
from datetime import timedelta
from statistics import mean
from sqlalchemy import func, select

from backend.app.analytics.metrics import numeric_summary, spearman_summary
from backend.app.core.clock import iso_z, parse_github_datetime
from backend.app.core.exceptions import AppError
from backend.app.persistence.models import Dataset, DatasetRepository, Repository
from backend.app.services.insights import repository_insights, repository_insights_for_window

INSIGHT_FIELDS = {'commits_weekly_mean': ('commit_activity', 'commits/week'), 'issue_median_hours': ('issue_resolution', 'hours'), 'pr_median_hours': ('pr_merges', 'hours'), 'release_interval_days': ('release_cadence', 'days')}


def metric_value(result, key):
    metric = result['insights'].get(INSIGHT_FIELDS[key][0])
    if not metric or metric['quality']['status'] != 'ready':
        return None
    if key == 'commits_weekly_mean':
        points = [p['value'] for p in metric['weekly'] if p['quality'] == 'ready']
        return mean(points) if points else None
    return metric.get('median_interval_days' if key == 'release_interval_days' else 'median_hours')


def compare_insights(session, ids, mode='same_period', window_days=90):
    if not 2 <= len(ids) <= 5 or len(set(ids)) != len(ids):
        raise AppError(422, 'VALIDATION_ERROR', '请选择2–5个不同仓库')
    if mode not in {'same_period', 'individual_periods'}:
        raise AppError(422, 'VALIDATION_ERROR', '不支持的对比方式')
    if window_days not in {30, 90, 180}:
        raise AppError(422, 'VALIDATION_ERROR', '分析范围只支持 30、90 或 180 天')
    results = [repository_insights(session, id, window_days=window_days) for id in ids]
    repos = [session.get(Repository, id) for id in ids]
    candidate_windows = [(result['window_start'], result['window_end']) for result in results]
    comparison_basis = {
        'scope': 'shared_observation' if mode == 'same_period' else 'repository_windows',
        'requested_window_days': window_days,
        'shared_window': None,
        'effective_days': None,
        'minimum_coverage_ratio': 0.8 if mode == 'same_period' else None,
        'minimum_effective_days': round(window_days * 0.8, 6) if mode == 'same_period' else None,
        'status': 'separate_windows' if mode == 'individual_periods' else 'not_comparable',
        'reason_code': 'INDIVIDUAL_WINDOWS_ASYNC' if mode == 'individual_periods' else 'MISSING_REPOSITORY_WINDOW',
        'reason': '各仓库分别使用自身分析窗口；结果不代表同期对比。' if mode == 'individual_periods' else '至少一个仓库没有覆盖所选窗口的分析运行。',
    }
    shared_start = shared_end = None
    if mode == 'same_period' and all(result['window_available'] for result in results):
        starts = [parse_github_datetime(start) for start, _ in candidate_windows]
        ends = [parse_github_datetime(end) for _, end in candidate_windows]
        if all(starts) and all(ends):
            shared_start, shared_end = max(starts), min(ends)
            if shared_end <= shared_start:
                shared_start = shared_end = None
                comparison_basis.update({
                    'reason_code': 'NO_SHARED_WINDOW',
                    'reason': '所选仓库的分析窗口没有时间交集。',
                })
            else:
                effective_days = (shared_end - shared_start).total_seconds() / 86400
                comparison_basis['shared_window'] = {'start': iso_z(shared_start), 'end': iso_z(shared_end)}
                comparison_basis['effective_days'] = round(effective_days, 6)
                if effective_days + 1e-9 >= window_days * 0.8:
                    comparison_basis.update({'status': 'comparable', 'reason_code': None, 'reason': None})
                    results = [repository_insights_for_window(session, result['repository_id'], shared_start, shared_end, result) for result in results]
                else:
                    comparison_basis.update({
                        'reason_code': 'SHARED_WINDOW_BELOW_THRESHOLD',
                        'reason': f'共同观察窗口为 {effective_days:.1f} 天，少于所选 {window_days} 天窗口的 80%。',
                    })

    common_weeks = None
    for result in results:
        weeks = {p['start'] for p in result['insights'].get('commit_activity', {}).get('weekly', []) if p['complete_week'] and p['quality'] == 'ready' and p['value'] is not None}
        common_weeks = weeks if common_weeks is None else common_weeks & weeks
    warnings = ['项目类型未分类；活动规模与处理耗时不能直接判定项目优劣。']
    if len({r.language for r in repos}) > 1:
        warnings.append('仓库主语言不同，请确认用途相近。')
    windows = set(candidate_windows)
    same_observation_window = len(windows) == 1 and all(result['window_available'] for result in results)
    if mode == 'same_period' and comparison_basis['status'] != 'comparable':
        warnings.append(comparison_basis['reason'])
    elif mode == 'individual_periods' and not same_observation_window:
        warnings.append('各仓库分别使用自身最近一次分析中的完整周与可用指标；观察窗口可能不同，适合查看各自活跃度和处理节奏，不代表同期对比。')
    rows = []
    for repo, result in zip(repos, results):
        if not result.get('window_available', result.get('run_id') is not None):
            warnings.append(f"{repo.full_name}：{result['window_reason']}")
        values = {}
        metric = result['insights'].get('commit_activity')
        ready_weeks = [
            point
            for point in (metric or {}).get('weekly', [])
            if point['complete_week'] and point['quality'] == 'ready' and point['value'] is not None
        ]
        selected_weeks = ready_weeks if mode == 'individual_periods' else [
            point for point in ready_weeks if point['start'] in (common_weeks or set())
        ]
        weekly_commits = selected_weeks
        for key, (name, unit) in INSIGHT_FIELDS.items():
            metric = result['insights'].get(name)
            value = metric_value(result, key)
            comparable = (mode == 'individual_periods' or comparison_basis['status'] == 'comparable') and value is not None
            start, end = (metric['window_start'], metric['window_end']) if metric else (None, None)
            if key == 'commits_weekly_mean':
                points = selected_weeks
                value = mean(p['value'] for p in points) if points else None
                comparable = value is not None
                start, end = (points[0]['start'], points[-1]['end']) if points else (None, None)
            if mode == 'same_period' and comparison_basis['status'] != 'comparable':
                comparable = False
            if comparison_basis['status'] == 'not_comparable' and mode == 'same_period':
                reason_code = comparison_basis['reason_code']
            elif key == 'commits_weekly_mean' and value is None and metric and metric['quality']['status'] == 'ready':
                reason_code = 'NO_COMMON_COMPLETE_UTC_WEEK' if mode == 'same_period' else 'NO_COMPLETE_UTC_WEEK'
            elif metric and metric['quality']['status'] != 'ready':
                reason_code = 'METRIC_QUALITY_NOT_READY'
            elif value is None:
                reason_code = 'NO_VALID_SAMPLES'
            else:
                reason_code = None
            values[key] = {
                'value': value if comparable else None,
                'unit': unit,
                'comparable': comparable,
                'valid_samples': sum(p['value'] for p in points) if key == 'commits_weekly_mean' else metric['quality']['valid_samples'] if metric else 0,
                'quality': metric['quality']['status'] if metric else 'missing',
                'reason_code': reason_code,
                'reason': comparison_basis['reason'] if reason_code in {'NO_SHARED_WINDOW', 'MISSING_REPOSITORY_WINDOW', 'SHARED_WINDOW_BELOW_THRESHOLD'} else metric['quality'].get('reason') if metric else None,
                'window_start': start,
                'window_end': end,
            }
        original_start, original_end = candidate_windows[len(rows)]
        rows.append({
            'repository_id': repo.repository_id,
            'full_name': repo.full_name,
            'language': repo.language,
            'created_at': iso_z(repo.created_at),
            'analyzed_at': result['analyzed_at'],
            'run_id': result['run_id'],
            'window_start': result['window_start'],
            'window_end': result['window_end'],
            'source_window_start': original_start,
            'source_window_end': original_end,
            'window_available': result.get('window_available', result.get('run_id') is not None),
            'window_reason': result.get('window_reason'),
            'metrics': values,
            'weekly_commits': weekly_commits,
        })
    return {'metric_version': 'insights-v1', 'timezone': 'UTC', 'mode': mode, 'requested_window_days': window_days, 'comparison_basis': comparison_basis, 'common_complete_weeks': len(common_weeks or []), 'repositories': rows, 'warnings': warnings}


def research_insights(session, dataset_id, analysis_mode='formal'):
    dataset = session.get(Dataset, dataset_id)
    expected_type = {'formal': 'research', 'exploratory': 'featured'}.get(analysis_mode)
    if expected_type is None:
        raise AppError(422, 'VALIDATION_ERROR', '不支持的研究分析模式')
    if dataset is None or dataset.type != expected_type:
        label = '研究数据集' if analysis_mode == 'formal' else '精选数据集'
        raise AppError(422, 'VALIDATION_ERROR', f'当前模式必须选择{label}')
    ids = session.scalars(select(DatasetRepository.repository_id).where(DatasetRepository.dataset_id == dataset_id, DatasetRepository.exclusion_status.is_(None)).order_by(DatasetRepository.repository_id)).all()
    membership_count = session.scalar(select(func.count()).select_from(DatasetRepository).where(DatasetRepository.dataset_id == dataset_id)) or 0
    rows = []
    windows = set()
    for id in ids:
        result = repository_insights(session, id, window_days=None)
        repo = session.get(Repository, id)
        values = {}
        metric_quality = {}
        for key, (name, _unit) in INSIGHT_FIELDS.items():
            metric = result['insights'].get(name)
            quality = metric.get('quality', {}) if metric else {}
            values[key] = metric_value(result, key)
            metric_quality[key] = {
                'status': quality.get('status', 'missing'),
                'coverage': quality.get('coverage', 'not_collected'),
                'valid_samples': quality.get('valid_samples', 0),
                'reason': quality.get('reason') or ('尚无事件级分析运行' if not result['run_id'] else '没有达到当前指标的有效样本'),
            }
        rows.append({'repository_id': id, 'full_name': repo.full_name, 'language': repo.language or '未知', 'analyzed_at': result['analyzed_at'], 'window_start': result['window_start'], 'window_end': result['window_end'], 'run_id': result['run_id'], 'values': values, 'metric_quality': metric_quality})
        if result['run_id']:
            windows.add((result['window_start'], result['window_end']))
    summary = {}
    metric_quality_summary = {}
    groups = []
    for key in INSIGHT_FIELDS:
        values = [r['values'][key] for r in rows if r['values'][key] is not None]
        summary[key] = {**numeric_summary(values), 'missing_count': len(rows) - len(values), 'missing_rate': (len(rows) - len(values)) / len(rows) if rows else None, 'unit': INSIGHT_FIELDS[key][1]}
        reasons = Counter(row['metric_quality'][key]['reason'] for row in rows if row['values'][key] is None)
        statuses = Counter(row['metric_quality'][key]['status'] for row in rows)
        metric_quality_summary[key] = {
            'valid_samples': len(values),
            'missing_count': len(rows) - len(values),
            'missing_rate': (len(rows) - len(values)) / len(rows) if rows else None,
            'status_counts': dict(sorted(statuses.items())),
            'missing_reasons': [{'reason': reason, 'count': count} for reason, count in sorted(reasons.items())],
        }
    for language in sorted({r['language'] for r in rows}):
        members = [r for r in rows if r['language'] == language]
        groups.append({'language': language, 'n': len(members), 'metrics': {key: numeric_summary([r['values'][key] for r in members if r['values'][key] is not None]) for key in INSIGHT_FIELDS}})
    paired = [r for r in rows if r['values']['issue_median_hours'] is not None and r['values']['pr_median_hours'] is not None]
    correlation = spearman_summary([r['values']['issue_median_hours'] for r in paired], [r['values']['pr_median_hours'] for r in paired]) if len(windows) <= 1 else {'n': len(paired), 'coefficient': None, 'p_value': None, 'note': '观察窗口不同，不计算相关性'}
    source_metadata = {}
    if dataset.source_metadata_json:
        try:
            source_metadata = json.loads(dataset.source_metadata_json)
        except (TypeError, ValueError):
            source_metadata = {}
    analyzable_members = sum(row['run_id'] is not None for row in rows)
    if analysis_mode == 'exploratory':
        dataset_status = 'analyzable' if analyzable_members else 'awaiting_collection'
        population_scope = 'curated_featured'
        limitations = [
            '精选数据集是策展样本，不是概率抽样；不得将结果外推为 GitHub 全体。',
            '只读取本地已保存的最新事件分析，不会因打开页面而请求 GitHub。',
            '仅ready输入进入指标；不同仓库采集时间可能不同，相关不代表因果。',
            '不足10个有效配对或变量无变化时不计算 Spearman。',
        ]
    else:
        dataset_status = 'pending_confirmation' if dataset.frozen_at is None else 'approved_not_imported' if membership_count == 0 else 'awaiting_collection' if analyzable_members == 0 else 'analyzable'
        population_scope = 'formal_research_sample'
        limitations = [
            '只分析当前研究成员的最新事件结果；冻结的是成员规则，不是永久锁定指标。',
            '仅ready输入进入分布；不同采集日期可能引入时间偏差，不代表GitHub总体，相关不代表因果。',
            '不足10个有效配对或变量无变化时不计算 Spearman。',
        ]
    return {
        'dataset_id': dataset_id,
        'analysis_mode': analysis_mode,
        'dataset_status': dataset_status,
        'population_scope': population_scope,
        'is_probability_sample': False,
        'dataset_version': source_metadata.get('version') or dataset.rules_version,
        'source': source_metadata.get('source') or dataset.description,
        'metric_version': 'insights-v1',
        'frozen_at': iso_z(dataset.frozen_at),
        'sample_size': len(rows),
        'analyzable_members': analyzable_members,
        'summary': summary,
        'metric_quality': metric_quality_summary,
        'groups': groups,
        'rows': rows,
        'correlation': correlation,
        'limitations': limitations,
    }
