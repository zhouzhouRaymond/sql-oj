import { ElMessage, ElMessageBox } from 'element-plus'
import router from '../router'
import { useUserStore } from '../stores/user'

/**
 * 退出登录：确认弹窗 → 清会话 → 回登录页 → 轻提示。
 *
 * 学生端各页面顶部的「退出」按钮共用这一份实现（避免每页各写一遍），
 * 文案可通过 options 定制（考试结果页的「唯一出口」语义不同）。
 */
export const confirmLogout = (options: {
  message?: string
  confirmText?: string
  successText?: string
} = {}) => {
  ElMessageBox.confirm(options.message || '确定要退出登录吗？', '提示', {
    confirmButtonText: options.confirmText || '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(() => {
    useUserStore().logout()
    router.push('/login')
    ElMessage.success(options.successText || '已退出登录')
  }).catch(() => {
    // 用户取消，不做任何事
  })
}
