import { computed, ref } from 'vue'

export type WebRole = 'student' | 'counselor' | 'administrator'
export interface DevelopmentIdentity { userId: string; sessionId: string; role: WebRole; displayName: string }

const storageKey = 'zhq-development-identity'
const defaults: DevelopmentIdentity = { userId: 'demo-student', sessionId: 'web-session-001', role: 'student', displayName: '同学' }

function loadIdentity(): DevelopmentIdentity {
  try {
    const stored = localStorage.getItem(storageKey)
    if (!stored) return defaults
    const parsed = JSON.parse(stored) as Partial<DevelopmentIdentity>
    return { ...defaults, ...parsed }
  } catch {
    return defaults
  }
}

const identity = ref<DevelopmentIdentity>(loadIdentity())

/** Temporary browser identity store; production uses verified SSO/JWT claims instead. */
export function useIdentity() {
  const label = computed(() => `${identity.value.displayName} · ${identity.value.role === 'student' ? '学生端' : identity.value.role}`)
  function update(next: Partial<DevelopmentIdentity>) {
    identity.value = { ...identity.value, ...next }
    try {
      localStorage.setItem(storageKey, JSON.stringify(identity.value))
    } catch {
      // Storage may be full or blocked; keep in-memory identity usable.
    }
  }
  return { identity, label, update }
}
