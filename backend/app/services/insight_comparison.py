from statistics import mean
from sqlalchemy import select

from backend.app.analytics.metrics import numeric_summary, spearman_summary
from backend.app.core.clock import iso_z
from backend.app.core.exceptions import AppError
from backend.app.persistence.models import Dataset, DatasetRepository, Repository
from backend.app.services.insights import repository_insights

INSIGHT_FIELDS = {'commits_weekly_mean': ('commit_activity', 'commits/week'), 'issue_median_hours': ('issue_resolution', 'hours'), 'pr_median_hours': ('pr_merges', 'hours'), 'release_interval_days': ('release_cadence', 'days')}


def metric_value(result, key):
    metric = result['insights'].get(INSIGHT_FIELDS[key][0])
    if not metric or metric['quality']['status'] != 'ready':
        return None
    if key == 'commits_weekly_mean':
        points = [p['value'] for p in metric['weekly'] if p['quality'] == 'ready']
        return mean(points) if points else None
    return metric.get('median_interval_days' if key == 'release_interval_days' else 'median_hours')


def compare_insights(session, ids):
    if not 2 <= len(ids) <= 5 or len(set(ids)) != len(ids):
        raise AppError(422, 'VALIDATION_ERROR', '请选择2–5个不同仓库')
    results = [repository_insights(session, id) for id in ids]
    repos = [session.get(Repository, id) for id in ids]
    common_weeks = None
    for result in results:
        weeks = {p['start'] for p in result['insights'].get('commit_activity', {}).get('weekly', []) if p['quality'] == 'ready'}
        common_weeks = weeks if common_weeks is None else common_weeks & weeks
    warnings = ['项目类型未分类；活动规模与处理耗时不能直接判定项目优劣。']
    if len({r.language for r in repos}) > 1:
        warnings.append('仓库主语言不同，请确认用途相近。')
    windows = {(r['window_start'], r['window_end']) for r in results}
    same_window = len(windows) == 1 and all(r['run_id'] for r in results)
    if not same_window:
        warnings.append('缺少观察窗口或窗口不一致；耗时与发布间隔不作同口径数值比较。Commit仅比较共同完整自然周。')
    rows = []
    for repo, result in zip(repos, results):
        values = {}
        weekly_commits = [
            point
            for point in result['insights'].get('commit_activity', {}).get('weekly', [])
            if point['start'] in (common_weeks or set()) and point['quality'] == 'ready'
        ]
        for key, (name, unit) in INSIGHT_FIELDS.items():
            metric = result['insights'].get(name)
            value = metric_value(result, key)
            comparable = same_window and value is not None
            start, end = (metric['window_start'], metric['window_end']) if metric else (None, None)
            if key == 'commits_weekly_mean':
                points = [p for p in (metric or {}).get('weekly', []) if p['start'] in (common_weeks or set())]
                value = mean(p['value'] for p in points) if points else None
                comparable = value is not None
                start, end = (points[0]['start'], points[-1]['end']) if points else (None, None)
            values[key] = {'value': value if comparable else None, 'unit': unit, 'comparable': comparable, 'valid_samples': sum(p['value'] for p in points) if key == 'commits_weekly_mean' else metric['quality']['valid_samples'] if metric else 0, 'quality': metric['quality']['status'] if metric else 'missing', 'window_start': start, 'window_end': end}
        rows.append({'repository_id': repo.repository_id, 'full_name': repo.full_name, 'language': repo.language, 'created_at': iso_z(repo.created_at), 'analyzed_at': result['analyzed_at'], 'run_id': result['run_id'], 'metrics': values, 'weekly_commits': weekly_commits})
    return {'metric_version': 'insights-v1', 'timezone': 'UTC', 'common_complete_weeks': len(common_weeks or []), 'repositories': rows, 'warnings': warnings}


def research_insights(session, dataset_id):
    dataset = session.get(Dataset, dataset_id)
    if dataset is None or dataset.type != 'research':
        raise AppError(422, 'VALIDATION_ERROR', '必须选择研究数据集')
    ids = session.scalars(select(DatasetRepository.repository_id).where(DatasetRepository.dataset_id == dataset_id, DatasetRepository.exclusion_status.is_(None)).order_by(DatasetRepository.repository_id)).all()
    rows = []
    windows = set()
    for id in ids:
        result = repository_insights(session, id)
        repo = session.get(Repository, id)
        rows.append({'repository_id': id, 'full_name': repo.full_name, 'language': repo.language or '未知', 'analyzed_at': result['analyzed_at'], 'window_start': result['window_start'], 'window_end': result['window_end'], 'run_id': result['run_id'], 'values': {key: metric_value(result, key) for key in INSIGHT_FIELDS}})
        if result['run_id']:
            windows.add((result['window_start'], result['window_end']))
    summary = {}
    groups = []
    for key in INSIGHT_FIELDS:
        values = [r['values'][key] for r in rows if r['values'][key] is not None]
        summary[key] = {**numeric_summary(values), 'missing_count': len(rows) - len(values), 'missing_rate': (len(rows) - len(values)) / len(rows) if rows else None, 'unit': INSIGHT_FIELDS[key][1]}
    for language in sorted({r['language'] for r in rows}):
        members = [r for r in rows if r['language'] == language]
        groups.append({'language': language, 'n': len(members), 'metrics': {key: numeric_summary([r['values'][key] for r in members if r['values'][key] is not None]) for key in INSIGHT_FIELDS}})
    paired = [r for r in rows if r['values']['issue_median_hours'] is not None and r['values']['pr_median_hours'] is not None]
    correlation = spearman_summary([r['values']['issue_median_hours'] for r in paired], [r['values']['pr_median_hours'] for r in paired]) if len(windows) <= 1 else {'n': len(paired), 'coefficient': None, 'p_value': None, 'note': '观察窗口不同，不计算相关性'}
    return {'dataset_id': dataset_id, 'metric_version': 'insights-v1', 'frozen_at': iso_z(dataset.frozen_at), 'sample_size': len(rows), 'summary': summary, 'groups': groups, 'rows': rows, 'correlation': correlation, 'limitations': ['只分析当前研究成员的最新事件结果；冻结的是成员规则，不是永久锁定指标。', '仅ready输入进入分布；不同采集日期可能引入时间偏差，不代表GitHub总体，相关不代表因果。', '不足10个有效配对或变量无变化时不计算Spearman。']}
