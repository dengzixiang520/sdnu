import { createRouter, createWebHashHistory } from 'vue-router'
import HomeDashboard from './components/HomeDashboard.vue'
import WellbeingSpace from './components/WellbeingSpace.vue'
import DormitoryDesk from './components/DormitoryDesk.vue'
import AcademicStudio from './components/AcademicStudio.vue'
import AcademicHub from './components/AcademicHub.vue'
import InterviewRoom from './components/InterviewRoom.vue'
import StudyPlan from './components/StudyPlan.vue'
import InnovationLab from './components/InnovationLab.vue'
import DocumentWorkshop from './components/DocumentWorkshop.vue'

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', component: HomeDashboard, meta: { section: '总览', title: '今日工作台' } },
    { path: '/wellbeing', component: WellbeingSpace, meta: { section: '学生服务', title: '暖心空间' } },
    { path: '/dormitory', component: DormitoryDesk, meta: { section: '生活协同', title: '宿舍与日程' } },
    { path: '/academic', component: AcademicHub, meta: { section: '学习成长', title: '选择今天要推进的事' } },
    { path: '/academic/interview', component: InterviewRoom, meta: { section: '学习成长', title: 'AI 模拟复试' } },
    { path: '/academic/notes', component: AcademicStudio, meta: { section: '学习成长', title: '笔记整理台' } },
    { path: '/academic/plan', component: StudyPlan, meta: { section: '学习成长', title: '学习计划' } },
    { path: '/innovation', component: InnovationLab, meta: { section: '创新实践', title: '竞赛孵化' } },
    { path: '/documents', component: DocumentWorkshop, meta: { section: '效率工具', title: '文档工坊' } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
