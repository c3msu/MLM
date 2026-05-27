'use client'

import { useState, useCallback, useEffect } from 'react'
import { User, UserPreferences } from '@/types/index'

interface AuthState {
  user: User | null
  isLoading: boolean
  isAuthenticated: boolean
}

interface LoginCredentials {
  email: string
  password: string
}

interface SignupData {
  email: string
  password: string
  name: string
}

// Mock user for development
const MOCK_USER: User = {
  id: '1',
  email: 'user@example.com',
  name: 'Demo User',
  avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=user',
  role: 'pro',
  createdAt: new Date('2024-01-01'),
  preferences: {
    theme: 'system',
    language: 'en',
    notifications: true,
    defaultTimeRange: '1Y',
  },
}

// Storage keys
const AUTH_STORAGE_KEY = 'the-dial-auth'
const USER_STORAGE_KEY = 'the-dial-user'

export function useAuth() {
  const [state, setState] = useState<AuthState>({
    user: null,
    isLoading: true,
    isAuthenticated: false,
  })

  // Initialize auth state from storage
  useEffect(() => {
    const initAuth = () => {
      try {
        const storedAuth = localStorage.getItem(AUTH_STORAGE_KEY)
        const storedUser = localStorage.getItem(USER_STORAGE_KEY)

        if (storedAuth === 'true' && storedUser) {
          const user = JSON.parse(storedUser)
          setState({
            user: { ...user, createdAt: new Date(user.createdAt) },
            isLoading: false,
            isAuthenticated: true,
          })
        } else {
          setState(prev => ({ ...prev, isLoading: false }))
        }
      } catch {
        setState(prev => ({ ...prev, isLoading: false }))
      }
    }

    initAuth()
  }, [])

  // Login function
  const login = useCallback(async (credentials: LoginCredentials): Promise<boolean> => {
    setState(prev => ({ ...prev, isLoading: true }))

    try {
      // Simulate API call
      await new Promise(resolve => setTimeout(resolve, 1000))

      // For demo, accept any email/password
      if (credentials.email && credentials.password) {
        const user = { ...MOCK_USER, email: credentials.email }
        
        localStorage.setItem(AUTH_STORAGE_KEY, 'true')
        localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user))
        
        setState({
          user,
          isLoading: false,
          isAuthenticated: true,
        })
        return true
      }
      
      setState(prev => ({ ...prev, isLoading: false }))
      return false
    } catch (error) {
      setState(prev => ({ ...prev, isLoading: false }))
      return false
    }
  }, [])

  // Signup function
  const signup = useCallback(async (data: SignupData): Promise<boolean> => {
    setState(prev => ({ ...prev, isLoading: true }))

    try {
      // Simulate API call
      await new Promise(resolve => setTimeout(resolve, 1000))

      const user: User = {
        ...MOCK_USER,
        email: data.email,
        name: data.name,
        role: 'free',
      }

      localStorage.setItem(AUTH_STORAGE_KEY, 'true')
      localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user))

      setState({
        user,
        isLoading: false,
        isAuthenticated: true,
      })
      return true
    } catch (error) {
      setState(prev => ({ ...prev, isLoading: false }))
      return false
    }
  }, [])

  // Logout function
  const logout = useCallback(() => {
    localStorage.removeItem(AUTH_STORAGE_KEY)
    localStorage.removeItem(USER_STORAGE_KEY)
    
    setState({
      user: null,
      isLoading: false,
      isAuthenticated: false,
    })
  }, [])

  // Update user preferences
  const updatePreferences = useCallback((preferences: Partial<UserPreferences>) => {
    setState(prev => {
      if (!prev.user) return prev

      const updatedUser = {
        ...prev.user,
        preferences: { ...prev.user.preferences, ...preferences },
      }

      localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(updatedUser))

      return {
        ...prev,
        user: updatedUser,
      }
    })
  }, [])

  // Update user profile
  const updateProfile = useCallback((data: Partial<Pick<User, 'name' | 'avatar'>>) => {
    setState(prev => {
      if (!prev.user) return prev

      const updatedUser = { ...prev.user, ...data }
      localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(updatedUser))

      return {
        ...prev,
        user: updatedUser,
      }
    })
  }, [])

  // Check if user has required role
  const hasRole = useCallback(
    (requiredRole: User['role'] | User['role'][]): boolean => {
      if (!state.user) return false
      
      const roles = Array.isArray(requiredRole) ? requiredRole : [requiredRole]
      const roleHierarchy: Record<User['role'], number> = {
        free: 0,
        pro: 1,
        enterprise: 2,
      }
      
      const userLevel = roleHierarchy[state.user.role]
      return roles.some(role => userLevel >= roleHierarchy[role])
    },
    [state.user]
  )

  return {
    ...state,
    login,
    signup,
    logout,
    updatePreferences,
    updateProfile,
    hasRole,
  }
}

// Hook for protected routes
export function useRequireAuth(redirectUrl: string = '/login') {
  const auth = useAuth()

  useEffect(() => {
    if (!auth.isLoading && !auth.isAuthenticated) {
      if (typeof window !== 'undefined') {
        window.location.href = redirectUrl
      }
    }
  }, [auth.isLoading, auth.isAuthenticated, redirectUrl])

  return auth
}
