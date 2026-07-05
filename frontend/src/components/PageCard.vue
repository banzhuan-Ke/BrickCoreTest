<template>
  <el-main class="page-card-host">
    <el-card class="page-card-panel" body-style="padding: 0 10px;">
      <!--标题-->
      <div class="title">
        <slot name="title"></slot>
      </div>
      <!-- 步骤列表-->
      <div class="main_box">
        <slot name="main"></slot>
      </div>
      <!-- 底部按钮-->
      <div class="bottom_box">
        <slot name="bottom"></slot>
      </div>
    </el-card>
  </el-main>
</template>

<script setup>
</script>

<style scoped lang="scss">
@use "./PageCard.scss";
</style>