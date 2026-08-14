<script setup lang="ts">
import { ref, computed } from 'vue'
import { PhFileText, PhDownload, PhEye, PhCopy, PhTrash } from '@phosphor-icons/vue'
import { command } from '../api'

interface DocumentElements {
  reference_number: string
  title: string
  body: string
  signature: string
  issue_date: string
}

const activeTab = ref<'editor' | 'templates' | 'history'>('editor')
const draft = ref('发文字号：鲁师字〔2026〕1号\n标题：关于开展人工智能创新应用大赛的通知\n正文：请各学院按要求组织师生积极参与。\n落款：教务处\n日期：2026年7月30日')
const elements = ref<DocumentElements | null>(null)
const message = ref('')
const loading = ref(false)
const selectedTemplate = ref('')
const documentHistory = ref<Array<{name: string, date: string, type: string}>>([])

const templates = [
  { id: 'notice', name: '通知', description: '学校各类通知文件', example: '发文字号：鲁师字〔2026〕X号\n标题：关于XXX的通知\n正文：...\n落款：XXX部门\n日期：2026年X月X日' },
  { id: 'announcement', name: '公告', description: '对外发布公告', example: '标题：山东师范大学XXX公告\n正文：...\n日期：2026年X月X日' },
  { id: 'report', name: '报告', description: '工作报告、调研报告', example: '标题：关于XXX的报告\n正文：\n一、基本情况\n二、存在问题\n三、建议措施\n落款：XXX\n日期：2026年X月X日' },
  { id: 'letter', name: '函', description: '商洽函、询问函', example: '发文字号：鲁师函〔2026〕X号\n标题：关于XXX的函\n正文：...\n落款：XXX\n日期：2026年X月X日' },
  { id: 'resolution', name: '决定', description: '表彰决定、处分决定', example: '发文字号：鲁师字〔2026〕X号\n标题：关于XXX的决定\n正文：...\n落款：XXX\n日期：2026年X月X日' },
]

async function parseDraft() {
  loading.value = true
  message.value = ''
  try {
    const result = await command('document_engine', 'extract_elements', draft.value)
    elements.value = result.data as unknown as DocumentElements
    message.value = result.message
  } catch (error) {
    message.value = error instanceof Error ? error.message : '解析失败'
  } finally {
    loading.value = false
  }
}

async function exportDocx() {
  if (!elements.value) {
    message.value = '请先解析草稿'
    return
  }
  
  loading.value = true
  try {
    const response = await fetch('/api/v1/documents/export-docx', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(elements.value)
    })
    
    if (response.ok) {
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${elements.value.title || '文档'}.docx`
      a.click()
      URL.revokeObjectURL(url)
      message.value = 'DOCX文件已导出'
      
      // 添加到历史记录
      documentHistory.value.unshift({
        name: elements.value.title || '未命名文档',
        date: new Date().toLocaleString('zh-CN'),
        type: 'DOCX'
      })
    } else {
      message.value = '导出失败'
    }
  } catch (error) {
    message.value = '导出失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

function useTemplate(template: typeof templates[0]) {
  draft.value = template.example
  selectedTemplate.value = template.id
  activeTab.value = 'editor'
}

function clearDraft() {
  draft.value = ''
  elements.value = null
  message.value = ''
}

function copyDraft() {
  navigator.clipboard.writeText(draft.value)
  message.value = '已复制到剪贴板'
}
</script>

<template>
  <section class="document-page">
    <header class="document-head">
      <div>
        <p class="eyebrow">效率工具 / 文档工坊</p>
        <h1>公文排版，<em>一键导出。</em></h1>
        <p>支持公文要素提取、DOCX导出、模板选择</p>
      </div>
    </header>

    <!-- 标签页 -->
    <div class="document-tabs">
      <button :class="{ active: activeTab === 'editor' }" @click="activeTab = 'editor'">
        <PhFileText :size="16" /> 文档编辑
      </button>
      <button :class="{ active: activeTab === 'templates' }" @click="activeTab = 'templates'">
        <PhCopy :size="16" /> 公文模板
      </button>
      <button :class="{ active: activeTab === 'history' }" @click="activeTab = 'history'">
        <PhFileText :size="16" /> 历史记录
      </button>
    </div>

    <!-- 文档编辑 -->
    <div v-if="activeTab === 'editor'" class="document-grid">
      <article class="draft-card">
        <div class="card-header">
          <p class="micro">01 / 原始草稿</p>
          <div class="card-actions">
            <button class="icon-btn" @click="copyDraft" title="复制"><PhCopy :size="16" /></button>
            <button class="icon-btn" @click="clearDraft" title="清空"><PhTrash :size="16" /></button>
          </div>
        </div>
        <textarea v-model="draft" class="document-draft" placeholder="输入公文内容..."></textarea>
        <div class="card-footer">
          <button class="ink-button" @click="parseDraft" :disabled="loading || !draft.trim()">
            {{ loading ? '解析中...' : '解析草稿' }}
          </button>
          <button class="ink-button primary" @click="exportDocx" :disabled="loading || !elements">
            <PhDownload :size="16" /> 导出 DOCX
          </button>
        </div>
        <p class="form-hint">{{ message || '输入公文内容，点击解析后可导出为DOCX文件' }}</p>
      </article>

      <article class="preview-card">
        <p class="micro">02 / 结构预览</p>
        <template v-if="elements">
          <div class="red-rule"></div>
          <p class="reference">{{ elements.reference_number }}</p>
          <h2>{{ elements.title }}</h2>
          <p class="body-preview">{{ elements.body }}</p>
          <div class="signature-block">
            <p class="signature">{{ elements.signature }}</p>
            <p class="issue-date">{{ elements.issue_date }}</p>
          </div>
        </template>
        <div v-else class="empty-preview">
          <PhEye :size="48" />
          <p>尚未解析</p>
          <small>系统将识别文号、标题、正文、落款与日期</small>
        </div>
      </article>
    </div>

    <!-- 公文模板 -->
    <div v-if="activeTab === 'templates'" class="templates-grid">
      <div v-for="template in templates" :key="template.id" class="template-card" @click="useTemplate(template)">
        <div class="template-icon">📄</div>
        <div class="template-info">
          <h3>{{ template.name }}</h3>
          <p>{{ template.description }}</p>
        </div>
        <button class="use-btn">使用模板</button>
      </div>
    </div>

    <!-- 历史记录 -->
    <div v-if="activeTab === 'history'" class="history-section">
      <div v-if="documentHistory.length === 0" class="empty-state">
        <PhFileText :size="48" />
        <p>暂无历史记录</p>
        <small>导出的文档将显示在这里</small>
      </div>
      <div v-else class="history-list">
        <div v-for="(item, index) in documentHistory" :key="index" class="history-item">
          <div class="history-icon">📄</div>
          <div class="history-info">
            <strong>{{ item.name }}</strong>
            <small>{{ item.date }} · {{ item.type }}</small>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>