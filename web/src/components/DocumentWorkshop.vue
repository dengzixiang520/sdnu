<script setup lang="ts">
import { ref } from 'vue'
import { command } from '../api'
const draft = ref('发文字号：鲁师字〔2026〕1号\n标题：关于开展人工智能创新应用大赛的通知\n正文：请各学院按要求组织师生积极参与。\n落款：教务处\n日期：2026年7月30日')
const elements = ref<Record<string, string>>({}); const message = ref('')
async function parse() { try { const result = await command('document_engine', 'extract_elements', draft.value); elements.value = result.data as Record<string, string>; message.value = result.message } catch (error) { message.value = error instanceof Error ? error.message : '解析失败' } }
</script>
<template><section class="document-page"><header class="document-head"><p class="eyebrow">效率工具 / 文档工坊</p><h1>提取公文要素，<em>检查结构。</em></h1></header><div class="document-grid"><article class="draft-card"><p class="micro">01 / 原始草稿</p><textarea v-model="draft" class="document-draft"></textarea><button class="ink-button" @click="parse">解析草稿</button><p class="form-hint">{{ message || '当前页面负责要素检查；DOCX 与 LaTeX 由受控文件任务生成。' }}</p></article><article class="preview-card"><p class="micro">02 / 结构预览</p><template v-if="Object.keys(elements).length"><div class="red-rule"></div><p class="reference">{{ elements.reference_number }}</p><h2>{{ elements.title }}</h2><p class="body-preview">{{ elements.body }}</p><p class="signature">{{ elements.signature }}<br />{{ elements.issue_date }}</p></template><p v-else class="empty-preview">尚未解析。<br />系统将识别文号、标题、正文、落款与日期。</p></article></div></section></template>
