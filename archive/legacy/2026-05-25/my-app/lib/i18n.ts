export const defaultLocale = 'en'
export const locales = ['en', 'zh']

export type Locale = (typeof locales)[number]

export const translations = {
  en: {
    common: {
      appName: 'The Dial',
      tagline: 'Macroeconomic Intelligence Dashboard',
      loading: 'Loading...',
      error: 'An error occurred',
      retry: 'Retry',
      cancel: 'Cancel',
      save: 'Save',
      delete: 'Delete',
      edit: 'Edit',
      close: 'Close',
      search: 'Search',
      filter: 'Filter',
      sort: 'Sort',
      export: 'Export',
      share: 'Share',
      settings: 'Settings',
      profile: 'Profile',
      logout: 'Logout',
      login: 'Login',
      signup: 'Sign Up',
      learnMore: 'Learn More',
      getStarted: 'Get Started',
      viewDetails: 'View Details',
      back: 'Back',
      next: 'Next',
      previous: 'Previous',
    },
    nav: {
      dashboard: 'Dashboard',
      modules: 'Modules',
      encyclopedia: 'Encyclopedia',
      calendar: 'Calendar',
      pricing: 'Pricing',
      about: 'About',
      contact: 'Contact',
    },
    dashboard: {
      title: 'Economic Dashboard',
      overallScore: 'Overall Score',
      lastUpdated: 'Last Updated',
      modules: 'Economic Modules',
      trends: 'Trends',
      factors: 'Key Factors',
      exportReport: 'Export Report',
      viewAllModules: 'View All Modules',
    },
    modules: {
      laborMarket: 'Labor Market',
      inflation: 'Inflation',
      gdpGrowth: 'GDP Growth',
      interestRates: 'Interest Rates',
      housingMarket: 'Housing Market',
      consumerSentiment: 'Consumer Sentiment',
      manufacturing: 'Manufacturing',
      internationalTrade: 'International Trade',
    },
    scores: {
      healthy: 'Healthy',
      warning: 'Warning',
      critical: 'Critical',
      improving: 'Improving',
      declining: 'Declining',
      stable: 'Stable',
      excellent: 'Excellent',
      good: 'Good',
      moderate: 'Moderate',
      weak: 'Weak',
      poor: 'Poor',
    },
    landing: {
      hero: {
        title: 'Understand the Economy at a Glance',
        subtitle: 'The Dial aggregates key macroeconomic indicators into a single, intuitive score that helps you understand economic conditions in real-time.',
      },
      features: {
        title: 'Powerful Features',
        subtitle: 'Everything you need to track and understand the economy',
      },
      howItWorks: {
        title: 'How It Works',
        subtitle: 'Simple, data-driven insights in three steps',
      },
      pricing: {
        title: 'Simple Pricing',
        subtitle: 'Choose the plan that fits your needs',
      },
    },
  },
  zh: {
    common: {
      appName: '经济仪表盘',
      tagline: '宏观经济智能仪表板',
      loading: '加载中...',
      error: '发生错误',
      retry: '重试',
      cancel: '取消',
      save: '保存',
      delete: '删除',
      edit: '编辑',
      close: '关闭',
      search: '搜索',
      filter: '筛选',
      sort: '排序',
      export: '导出',
      share: '分享',
      settings: '设置',
      profile: '个人资料',
      logout: '退出',
      login: '登录',
      signup: '注册',
      learnMore: '了解更多',
      getStarted: '开始使用',
      viewDetails: '查看详情',
      back: '返回',
      next: '下一步',
      previous: '上一步',
    },
    nav: {
      dashboard: '仪表板',
      modules: '模块',
      encyclopedia: '百科',
      calendar: '日历',
      pricing: '定价',
      about: '关于',
      contact: '联系',
    },
    dashboard: {
      title: '经济仪表板',
      overallScore: '综合评分',
      lastUpdated: '最后更新',
      modules: '经济模块',
      trends: '趋势',
      factors: '关键因素',
      exportReport: '导出报告',
      viewAllModules: '查看所有模块',
    },
    modules: {
      laborMarket: '劳动力市场',
      inflation: '通货膨胀',
      gdpGrowth: 'GDP增长',
      interestRates: '利率',
      housingMarket: '房地产市场',
      consumerSentiment: '消费者信心',
      manufacturing: '制造业',
      internationalTrade: '国际贸易',
    },
    scores: {
      healthy: '健康',
      warning: '警告',
      critical: '危急',
      improving: '改善中',
      declining: '下降中',
      stable: '稳定',
      excellent: '优秀',
      good: '良好',
      moderate: '中等',
      weak: '疲软',
      poor: '较差',
    },
    landing: {
      hero: {
        title: '一目了然了解经济',
        subtitle: '经济仪表盘将关键宏观经济指标整合为一个直观的评分，帮助您实时了解经济状况。',
      },
      features: {
        title: '强大功能',
        subtitle: '追踪和了解经济所需的一切',
      },
      howItWorks: {
        title: '工作原理',
        subtitle: '三个步骤，获得简单的数据驱动洞察',
      },
      pricing: {
        title: '简单定价',
        subtitle: '选择适合您需求的方案',
      },
    },
  },
}

export function getTranslation(locale: Locale, key: string): string {
  const keys = key.split('.')
  let value: unknown = translations[locale]
  
  for (const k of keys) {
    if (value && typeof value === 'object' && k in value) {
      value = (value as Record<string, unknown>)[k]
    } else {
      return key
    }
  }
  
  return typeof value === 'string' ? value : key
}

export function formatLocaleDate(date: Date, locale: Locale): string {
  return new Intl.DateTimeFormat(locale === 'zh' ? 'zh-CN' : 'en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(date)
}

export function formatLocaleNumber(number: number, locale: Locale): string {
  return new Intl.NumberFormat(locale === 'zh' ? 'zh-CN' : 'en-US').format(number)
}
