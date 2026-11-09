<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { PhShoppingBag, PhGift, PhTicket, PhCheckCircle, PhMapPin } from '@phosphor-icons/vue'
import { useIdentity } from '../identity'
import { requestJson } from '../api'

interface Product {
  id: string
  name: string
  description: string
  category: string
  points: number
  stock: number
  image: string
  location: string
}

interface ExchangeRecord {
  id: string
  user_id: string
  user_name: string
  product_id: string
  product_name: string
  points_cost: number
  exchange_code: string
  exchange_time: string
  pick_up_location: string
  status: string
}

const { identity } = useIdentity()
const products = ref<Product[]>([])
const exchanges = ref<ExchangeRecord[]>([])
const loading = ref(false)
const showConfirm = ref(false)
const selectedProduct = ref<Product | null>(null)
const exchangeResult = ref<any>(null)
const category = ref('全部')
const loadError = ref('')

const currentUserId = computed(() => identity.value.userId)
const currentUserName = computed(() => identity.value.displayName)

const categories = computed(() => {
  const cats = new Set(products.value.map(p => p.category))
  return ['全部', ...Array.from(cats)]
})

const filteredProducts = computed(() => {
  if (category.value === '全部') return products.value
  return products.value.filter(p => p.category === category.value)
})

async function fetchProducts() {
  try {
    const data = await requestJson<{ success: boolean; data: { products: Product[] } }>(
      '/api/v1/exchange/products', {}, '获取商品失败')
    if (data.success) products.value = data.data.products
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : '获取商品失败'
  }
}

async function fetchExchanges() {
  try {
    const data = await requestJson<{ success: boolean; data: { exchanges: ExchangeRecord[] } }>(
      `/api/v1/exchange/user/${currentUserId.value}`, {}, '获取兑换记录失败')
    if (data.success) exchanges.value = data.data.exchanges
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : '获取兑换记录失败'
  }
}

function selectProduct(product: Product) {
  selectedProduct.value = product
  showConfirm.value = true
  exchangeResult.value = null
}

async function confirmExchange() {
  if (!selectedProduct.value) return
  loading.value = true
  try {
    const data = await requestJson<{ success: boolean; data: Record<string, unknown> }>('/api/v1/exchange/redeem', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: currentUserId.value,
        user_name: currentUserName.value,
        product_id: selectedProduct.value.id
      })
    }, '兑换失败')
    if (data.success) {
      exchangeResult.value = data.data
      await fetchProducts()
      await fetchExchanges()
    } else {
      exchangeResult.value = { error: '兑换失败' }
    }
  } catch (err) {
    exchangeResult.value = { error: err instanceof Error ? err.message : '兑换失败，请稍后重试' }
  } finally {
    loading.value = false
  }
}

function closeConfirm() {
  showConfirm.value = false
  selectedProduct.value = null
  exchangeResult.value = null
}

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleString('zh-CN')
}

onMounted(() => {
  fetchProducts()
  fetchExchanges()
})
</script>

<template>
  <div class="exchange-shop">
    <div v-if="loadError" class="inline-error dismissible-error page-error" role="alert">
      <span>{{ loadError }}</span>
      <button type="button" @click="loadError = ''">知道了</button>
    </div>
    <!-- 分类筛选 -->
    <div class="exchange-categories">
      <button v-for="cat in categories" :key="cat" :class="{ active: category === cat }" @click="category = cat">
        {{ cat }}
      </button>
    </div>

    <!-- 商品列表 -->
    <div class="products-grid">
      <div v-for="product in filteredProducts" :key="product.id" class="product-card" :class="{ 'out-of-stock': product.stock === 0 }">
        <div class="product-image">{{ product.image }}</div>
        <div class="product-info">
          <h3>{{ product.name }}</h3>
          <p>{{ product.description }}</p>
          <div class="product-meta">
            <span class="product-points">{{ product.points }} 积分</span>
            <span class="product-stock">库存: {{ product.stock }}</span>
          </div>
          <div class="product-location">
            <PhMapPin :size="14" /> {{ product.location }}
          </div>
        </div>
        <button class="exchange-btn" @click="selectProduct(product)" :disabled="product.stock === 0">
          {{ product.stock === 0 ? '已售罄' : '立即兑换' }}
        </button>
      </div>
    </div>

    <!-- 我的兑换记录 -->
    <div class="exchange-records" v-if="exchanges.length > 0">
      <h3><PhTicket :size="20" /> 我的兑换记录</h3>
      <div class="records-list">
        <div v-for="record in exchanges" :key="record.id" class="record-item" :class="record.status">
          <div class="record-info">
            <span class="record-name">{{ record.product_name }}</span>
            <span class="record-time">{{ formatDate(record.exchange_time) }}</span>
          </div>
          <div class="record-code">
            <span class="code-label">兑换码</span>
            <span class="code-value">{{ record.exchange_code }}</span>
          </div>
          <div class="record-status">
            <span v-if="record.status === 'pending'" class="status-pending">待领取</span>
            <span v-else-if="record.status === 'claimed'" class="status-claimed">已领取</span>
            <span v-else class="status-expired">已过期</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 兑换确认弹窗 -->
    <div v-if="showConfirm" class="modal-overlay" @click.self="closeConfirm">
      <div class="modal-content">
        <template v-if="!exchangeResult">
          <h3>确认兑换</h3>
          <div class="confirm-product">
            <span class="confirm-image">{{ selectedProduct?.image }}</span>
            <div>
              <strong>{{ selectedProduct?.name }}</strong>
              <p>{{ selectedProduct?.description }}</p>
            </div>
          </div>
          <div class="confirm-details">
            <div class="detail-row">
              <span>所需积分</span>
              <span class="points-cost">{{ selectedProduct?.points }} 积分</span>
            </div>
            <div class="detail-row">
              <span>领取地点</span>
              <span>{{ selectedProduct?.location }}</span>
            </div>
          </div>
          <div class="confirm-actions">
            <button class="cancel-btn" @click="closeConfirm">取消</button>
            <button class="confirm-btn" @click="confirmExchange" :disabled="loading">
              {{ loading ? '兑换中...' : '确认兑换' }}
            </button>
          </div>
        </template>

        <template v-else-if="exchangeResult.error">
          <div class="error-result">
            <span class="error-icon">❌</span>
            <h3>兑换失败</h3>
            <p>{{ exchangeResult.error }}</p>
            <button @click="closeConfirm">关闭</button>
          </div>
        </template>

        <template v-else>
          <div class="success-result">
            <PhCheckCircle :size="48" class="success-icon" />
            <h3>兑换成功！</h3>
            <div class="result-details">
              <div class="result-row">
                <span>商品</span>
                <span>{{ exchangeResult.product_name }}</span>
              </div>
              <div class="result-row">
                <span>消耗积分</span>
                <span>{{ exchangeResult.points_cost }}</span>
              </div>
              <div class="result-row code-row">
                <span>兑换码</span>
                <span class="exchange-code">{{ exchangeResult.exchange_code }}</span>
              </div>
              <div class="result-row">
                <span>领取地点</span>
                <span>{{ exchangeResult.pick_up_location }}</span>
              </div>
            </div>
            <p class="result-tip">请凭兑换码到指定地点领取奖品</p>
            <button @click="closeConfirm">完成</button>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>