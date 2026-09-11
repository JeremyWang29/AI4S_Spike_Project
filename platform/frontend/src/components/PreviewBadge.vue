<script setup>
defineProps({label:{type:String,default:'交互预览 · 未连接真实服务'}})
</script>
<template><span class="preview-badge" aria-label="模拟内容来源">{{label}}</span></template>
