<script setup lang="ts">
import { ref } from 'vue'
import { api, errorText } from '../lib/api'
import { useQuery } from '../lib/query'
const users=useQuery<{id:number;username:string;role:string;status:string}[]>('/api/admin/users')
const username=ref(''),email=ref(''),password=ref(''),confirm=ref(''),busy=ref(false),message=ref(''),error=ref('')
async function create(){
  error.value='';message.value=''
  if(password.value!==confirm.value){error.value='两次密码不一致';return}
  busy.value=true
  try{await api('/api/admin/users',{method:'POST',body:{username:username.value.trim(),email:email.value.trim()||null,password:password.value,role:'member'}});message.value='成员账户已创建，可从登录页登录。';username.value='';email.value='';await users.reload()}
  catch(e){error.value=errorText(e)}finally{password.value='';confirm.value='';busy.value=false}
}
</script>
<template><section class="card section"><div class="card-header"><h2>用户管理</h2><small>仅管理员可见；新建成员不会改变当前登录</small></div><div class="card-body"><p v-if="error||users.error.value" role="alert">{{error||users.error.value}}</p><p v-if="message" role="status">{{message}}</p>
<form class="form-grid" @submit.prevent="create"><label class="field">新成员用户名<input v-model="username" autocomplete="off" maxlength="128" required></label><label class="field">新成员邮箱（可选）<input v-model="email" type="email" maxlength="320" autocomplete="off"></label><label class="field">新成员密码<input v-model="password" type="password" autocomplete="new-password" minlength="6" maxlength="1024" required></label><label class="field">确认新成员密码<input v-model="confirm" type="password" autocomplete="new-password" maxlength="1024" required></label><button class="button primary" :disabled="busy">创建成员账户</button></form>
<div class="table-scroll"><table><thead><tr><th>用户名</th><th>角色</th><th>状态</th></tr></thead><tbody><tr v-for="user in users.data.value" :key="user.id"><td>{{user.username}}</td><td>{{user.role}}</td><td>{{user.status}}</td></tr></tbody></table></div></div></section></template>
