import { defineStore } from 'pinia'
import { ref } from 'vue'
import client from '@/services/api/client'

export const useSetupStore = defineStore('setup', () => {
  const isComplete      = ref<boolean | null>(null)
  const hasAdmin        = ref(false)
  const currentStep     = ref(1)
  const totalSteps      = 7
  // Track which steps were explicitly completed (not skipped)
  // Using ref<number[]> (not Set) so Vue tracks array mutations reactively
  const completedSteps  = ref<number[]>([])

  async function checkStatus(): Promise<boolean> {
    try {
      const { data } = await client.get('/setup/status')
      isComplete.value = data.is_setup_complete === true
      hasAdmin.value   = data.has_admin === true
    } catch {
      isComplete.value = false
    }
    return isComplete.value!
  }

  function nextStep() {
    if (currentStep.value < totalSteps) currentStep.value++
  }

  function prevStep() {
    if (currentStep.value > 1) currentStep.value--
  }

  function goToStep(n: number) {
    currentStep.value = n
  }

  function markDone(step: number) {
    if (!completedSteps.value.includes(step)) {
      completedSteps.value = [...completedSteps.value, step]
    }
  }

  function isDone(step: number): boolean {
    return completedSteps.value.includes(step)
  }

  return { isComplete, hasAdmin, currentStep, totalSteps, completedSteps, checkStatus, nextStep, prevStep, goToStep, markDone, isDone }
})
