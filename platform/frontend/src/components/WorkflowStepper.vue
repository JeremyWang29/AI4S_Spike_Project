<script setup>
import {workflowSteps,statusLabel} from '../state.js'
defineProps({active:{type:Number,required:true},states:{type:Object,required:true}})
defineEmits(['select'])
</script>
<template>
  <ol class="stepper" aria-label="研究流程">
    <li v-for="(step,index) in workflowSteps" :key="step.id">
      <button :class="['step-button',{selected:active===index}]" @click="$emit('select',index)" :aria-current="active===index?'step':undefined">
        <span class="step-number">{{step.number}}</span>
        <span><b>{{step.short}}</b><small>{{statusLabel(states[step.id]||'locked')}}</small></span>
      </button>
    </li>
  </ol>
</template>
