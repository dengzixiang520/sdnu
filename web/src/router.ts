import { createRouter, createWebHashHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', component: () => import('./components/HomeDashboard.vue'), meta: { section: '总览', title: '今日工作台' } },
    { path: '/wellbeing', component: () => import('./components/WellbeingSpace.vue'), meta: { section: '学生服务', title: '暖心空间' } },
    { path: '/dormitory', component: () => import('./components/DormitoryDesk.vue'), meta: { section: '生活协同', title: '宿舍与日程' } },
    { path: '/academic', component: () => import('./components/AcademicHub.vue'), meta: { section: '学习成长', title: '选择今天要推进的事' } },
    { path: '/academic/interview', component: () => import('./components/InterviewRoom.vue'), meta: { section: '学习成长', title: 'AI 模拟复试' } },
    { path: '/academic/notes', component: () => import('./components/AcademicStudio.vue'), meta: { section: '学习成长', title: '笔记整理台' } },
    { path: '/academic/plan', component: () => import('./components/StudyPlan.vue'), meta: { section: '学习成长', title: '学习计划' } },
    { path: '/academic/credit', component: () => import('./components/AcademicCredit.vue'), meta: { section: '学习成长', title: '学业预警自检' } },
    { path: '/innovation', component: () => import('./components/InnovationLab.vue'), meta: { section: '创新实践', title: '竞赛孵化' } },
    { path: '/documents', component: () => import('./components/DocumentWorkshop.vue'), meta: { section: '效率工具', title: '文档工坊' } },
    { path: '/points', component: () => import('./components/PointsCenter.vue'), meta: { section: '成长激励', title: '积分中心' } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
