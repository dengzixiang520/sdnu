import { computed, ref } from 'vue'

export type WebRole = 'student' | 'counselor' | 'administrator'
export interface DevelopmentIdentity { userId: string; sessionId: string; role: WebRole; displayName: string }

const storageKey = 'zhq-development-identity'
const defaults: DevelopmentIdentity = { userId: 'demo-student', sessionId: 'web-session-001', role: 'student', displayName: '同学' }
const stored = localStorage.getItem(storageKey)
const identity = ref<DevelopmentIdentity>(stored ? { ...defaults, ...JSON.parse(stored) } : defaults)

/** Temporary browser identity store; production uses verified SSO/JWT claims instead. */
export function useIdentity() {
  const label = computed(() => `${identity.value.displayName} · ${identity.value.role === 'student' ? '学生端' : identity.value.role}`)
  function update(next: Partial<DevelopmentIdentity>) { identity.value = { ...identity.value, ...next }; localStorage.setItem(storageKey, JSON.stringify(identity.value)) }
  return { identity, label, update }
}
