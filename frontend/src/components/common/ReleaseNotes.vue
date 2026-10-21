<script setup lang="ts">
import { computed } from 'vue'
import DOMPurify from 'dompurify'
import { Marked } from 'marked'

const props = defineProps<{ body: string }>()

const markdown = new Marked({ async: false, gfm: true, breaks: false })
const alertLabels: Record<string, string> = {
  NOTE: '提示',
  TIP: '建议',
  IMPORTANT: '重要',
  WARNING: '警告',
  CAUTION: '注意',
}

const renderedBody = computed(() => {
  const source = props.body.replace(/^>\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*$/gim, (_, type: string) => `> **${alertLabels[type.toUpperCase()]}**`)
  const html = markdown.parse(source, { async: false })
  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
    ALLOWED_URI_REGEXP: /^(?:(?:https?:\/\/)|mailto:|\/|#)/i,
  })
})
</script>

<template>
  <div class="release-notes" v-html="renderedBody" />
</template>

<style scoped>
.release-notes :deep(> :first-child) { margin-top: 0; }
.release-notes :deep(> :last-child) { margin-bottom: 0; }
.release-notes :deep(h1),
.release-notes :deep(h2),
.release-notes :deep(h3),
.release-notes :deep(h4) {
  margin: 1.1em 0 0.45em;
  color: var(--gd-ink);
  font-weight: 650;
  line-height: 1.35;
}
.release-notes :deep(h1) { font-size: 1.2em; }
.release-notes :deep(h2) { font-size: 1.1em; }
.release-notes :deep(h3),
.release-notes :deep(h4) { font-size: 1em; }
.release-notes :deep(p) { margin: 0.65em 0; overflow-wrap: anywhere; }
.release-notes :deep(ul),
.release-notes :deep(ol) { margin: 0.65em 0; padding-left: 1.45em; }
.release-notes :deep(ul) { list-style: disc; }
.release-notes :deep(ol) { list-style: decimal; }
.release-notes :deep(li + li) { margin-top: 0.25em; }
.release-notes :deep(li > ul),
.release-notes :deep(li > ol) { margin: 0.3em 0; }
.release-notes :deep(blockquote) {
  margin: 0.85em 0;
  border-left: 3px solid var(--gd-s3);
  border-radius: 0 6px 6px 0;
  background: color-mix(in srgb, var(--gd-s3) 8%, transparent);
  padding: 0.45em 0.8em;
}
.release-notes :deep(blockquote > :first-child) { margin-top: 0; }
.release-notes :deep(blockquote > :last-child) { margin-bottom: 0; }
.release-notes :deep(a) {
  color: var(--gd-s3);
  overflow-wrap: anywhere;
  text-decoration: underline;
  text-underline-offset: 2px;
}
.release-notes :deep(code) {
  border-radius: 4px;
  background: color-mix(in srgb, var(--gd-ink) 8%, transparent);
  padding: 0.12em 0.35em;
  font-family: var(--font-mono);
  font-size: 0.92em;
  overflow-wrap: anywhere;
}
.release-notes :deep(pre) {
  overflow: auto;
  border: 1px solid var(--gd-border);
  border-radius: 6px;
  background: var(--gd-bg);
  padding: 0.75em;
}
.release-notes :deep(pre code) {
  background: transparent;
  padding: 0;
  overflow-wrap: normal;
}
.release-notes :deep(img) {
  display: block;
  max-width: 100%;
  height: auto !important;
  margin: 0.85em auto;
  border: 1px solid var(--gd-border);
  border-radius: 6px;
  object-fit: contain;
}
.release-notes :deep(table) {
  display: block;
  max-width: 100%;
  overflow-x: auto;
  border-collapse: collapse;
}
.release-notes :deep(th),
.release-notes :deep(td) { border: 1px solid var(--gd-border); padding: 0.35em 0.55em; }
.release-notes :deep(hr) { margin: 1em 0; border: 0; border-top: 1px solid var(--gd-border); }
</style>
