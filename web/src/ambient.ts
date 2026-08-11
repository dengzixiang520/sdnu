type AmbientKind = '雨声' | '钢琴' | '森林'

let context: AudioContext | null = null
let activeNodes: AudioNode[] = []
let pianoTimer: number | null = null
let masterGain: GainNode | null = null
let currentVolume = .45

function ensureContext() {
  context ??= new AudioContext()
  if (!masterGain) {
    masterGain = context.createGain()
    masterGain.gain.value = currentVolume
    masterGain.connect(context.destination)
  }
  return context
}

function clearNodes() {
  activeNodes.forEach((node) => { try { (node as AudioScheduledSourceNode).stop?.() } catch { /* already stopped */ } })
  activeNodes = []
  if (pianoTimer !== null) window.clearInterval(pianoTimer)
  pianoTimer = null
}

function noiseBuffer(audio: AudioContext) {
  const buffer = audio.createBuffer(1, audio.sampleRate * 2, audio.sampleRate)
  const channel = buffer.getChannelData(0)
  for (let index = 0; index < channel.length; index += 1) channel[index] = Math.random() * 2 - 1
  return buffer
}

/** Play a lightweight procedural ambience without remote audio files or tracking requests. */
export async function playAmbient(kind: AmbientKind) {
  stopAmbient()
  const audio = ensureContext()
  await audio.resume()
  if (kind === '钢琴') {
    const notes = [261.63, 329.63, 392, 493.88]
    let cursor = 0
    const playNote = () => {
      const oscillator = audio.createOscillator(); const gain = audio.createGain()
      oscillator.type = 'sine'; oscillator.frequency.value = notes[cursor++ % notes.length]
      gain.gain.setValueAtTime(0, audio.currentTime); gain.gain.linearRampToValueAtTime(.055, audio.currentTime + .05); gain.gain.exponentialRampToValueAtTime(.001, audio.currentTime + 2.6)
      oscillator.connect(gain).connect(masterGain!); oscillator.start(); oscillator.stop(audio.currentTime + 2.7)
    }
    playNote(); pianoTimer = window.setInterval(playNote, 3100); return
  }
  const source = audio.createBufferSource(); const filter = audio.createBiquadFilter(); const gain = audio.createGain()
  source.buffer = noiseBuffer(audio); source.loop = true
  filter.type = kind === '雨声' ? 'highpass' : 'lowpass'; filter.frequency.value = kind === '雨声' ? 1600 : 480
  gain.gain.value = kind === '雨声' ? .035 : .07
  source.connect(filter).connect(gain).connect(masterGain!); source.start(); activeNodes = [source, filter, gain]
}

export function stopAmbient() { clearNodes() }

/** Update procedural ambience volume without restarting playback. */
export function setAmbientVolume(value: number) {
  currentVolume = Math.max(0, Math.min(value, 1))
  if (masterGain && context) masterGain.gain.setTargetAtTime(currentVolume, context.currentTime, .03)
}
