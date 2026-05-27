/**
 * The Dial - Common JavaScript
 * Security: No eval, no innerHTML with user data, CSP compliant
 */

(function() {
  'use strict';

  // Theme Manager
  const ThemeManager = {
    init() {
      const saved = localStorage.getItem('theme');
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      
      if (saved === 'dark' || (!saved && prefersDark)) {
        document.documentElement.classList.add('dark');
      }
      
      // Listen for toggle clicks
      document.querySelectorAll('[data-theme-toggle]').forEach(btn => {
        btn.addEventListener('click', () => this.toggle());
      });
    },
    
    toggle() {
      const isDark = document.documentElement.classList.toggle('dark');
      localStorage.setItem('theme', isDark ? 'dark' : 'light');
    }
  };

  // Intersection Observer for animations
  const AnimationObserver = {
    init() {
      if (!('IntersectionObserver' in window)) {
        // Fallback: show all elements
        document.querySelectorAll('[data-animate]').forEach(el => {
          el.classList.add('animate-fade-in');
        });
        return;
      }
      
      const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            entry.target.classList.add('animate-fade-in');
            observer.unobserve(entry.target);
          }
        });
      }, {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
      });
      
      document.querySelectorAll('[data-animate]').forEach(el => {
        el.style.opacity = '0';
        observer.observe(el);
      });
    }
  };

  // Initialize Lucide icons safely
  const IconManager = {
    init() {
      if (typeof lucide !== 'undefined') {
        lucide.createIcons();
      }
    }
  };

  // Mobile Navigation
  const MobileNav = {
    init() {
      const toggle = document.querySelector('[data-mobile-toggle]');
      const menu = document.querySelector('[data-mobile-menu]');
      
      if (!toggle || !menu) return;
      
      toggle.addEventListener('click', () => {
        const isOpen = menu.classList.toggle('hidden');
        toggle.setAttribute('aria-expanded', !isOpen);
      });
      
      // Close on outside click
      document.addEventListener('click', (e) => {
        if (!menu.contains(e.target) && !toggle.contains(e.target)) {
          menu.classList.add('hidden');
          toggle.setAttribute('aria-expanded', 'false');
        }
      });
    }
  };

  // Initialize on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  function init() {
    ThemeManager.init();
    AnimationObserver.init();
    IconManager.init();
    MobileNav.init();
  }

  // Expose minimal API globally
  window.TheDial = {
    theme: ThemeManager
  };
})();
