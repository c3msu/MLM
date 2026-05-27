# The Dial - Technical Specification

## Project Overview

| Property | Value |
|----------|-------|
| **Name** | The Dial |
| **Type** | Macroeconomic Research Dashboard |
| **Stack** | React + TypeScript + Next.js + Tailwind CSS + shadcn/ui |
| **Version** | 1.0.0 |

---

## 1. Technology Stack

### 1.1 Frontend Framework

| Category | Technology | Version | Purpose |
|----------|------------|---------|---------|
| **Framework** | Next.js | 14+ | App Router, SSR/SSG, API routes |
| **UI Library** | React | 18+ | Component-based architecture |
| **Language** | TypeScript | 5+ | Type safety, IntelliSense |
| **Styling** | Tailwind CSS | 3.4+ | Utility-first CSS |
| **Components** | shadcn/ui | Latest | Accessible UI primitives |
| **Icons** | Lucide React | Latest | Consistent icon system |

### 1.2 State Management

| Category | Technology | Purpose |
|----------|------------|---------|
| **Server State** | TanStack Query (React Query) | API data fetching, caching, synchronization |
| **Client State** | Zustand | Global UI state, user preferences |
| **Form State** | React Hook Form | Form handling, validation |
| **Validation** | Zod | Schema validation, type inference |

### 1.3 Data Visualization

| Category | Technology | Purpose |
|----------|------------|---------|
| **Charts** | Recharts | Line charts, area charts, bar charts |
| **Grid Layout** | react-grid-layout | Draggable dashboard grid |
| **Custom SVG** | Native SVG | Gauge component, custom visualizations |

### 1.4 Animation Libraries

| Category | Technology | Purpose |
|----------|------------|---------|
| **Primary** | Framer Motion | Page transitions, gestures, spring animations |
| **Secondary** | CSS Animations | Simple hover effects, micro-interactions |
| **Custom** | Custom Hooks | Animated counters, scroll reveals |

### 1.5 Data Integration

| Category | Technology | Purpose |
|----------|------------|---------|
| **API Client** | Axios | HTTP requests, interceptors |
| **Data Source** | FRED API | Federal Reserve Economic Data |
| **Date Handling** | date-fns | Date manipulation, formatting |

### 1.6 Export Functionality

| Category | Technology | Purpose |
|----------|------------|---------|
| **PDF** | jsPDF + html2canvas | PDF report generation |
| **Excel** | xlsx | XLSX file export |
| **CSV** | Native | CSV data export |

### 1.7 Authentication & Theming

| Category | Technology | Purpose |
|----------|------------|---------|
| **Auth** | NextAuth.js | OAuth, JWT, session management |
| **Theming** | next-themes | Light/dark mode |
| **i18n** | next-intl | Internationalization, localization |

### 1.8 Backend/Database (Future)

| Category | Technology | Purpose |
|----------|------------|---------|
| **Database** | PostgreSQL | Primary data store |
| **ORM** | Prisma | Database access, migrations |
| **Cache** | Redis | Session store, rate limiting |

---

## 2. Component Inventory

### 2.1 shadcn/ui Components (Built-in)

| Component | Purpose | Customization |
|-----------|---------|---------------|
| `accordion` | FAQ section, expandable content | Custom animation timing |
| `alert` | Error messages, notifications | Color variants |
| `alert-dialog` | Confirmation dialogs | - |
| `avatar` | User profile images | Size variants |
| `badge` | Status indicators, labels | Score color coding |
| `button` | Primary actions | Loading states |
| `card` | Content containers | Hover effects |
| `checkbox` | Form inputs | - |
| `collapsible` | Expandable sections | - |
| `command` | Command palette, search | - |
| `dialog` | Modals, popups | Animation overrides |
| `dropdown-menu` | Navigation menus | - |
| `form` | Form wrapper | React Hook Form integration |
| `input` | Text inputs | - |
| `label` | Form labels | - |
| `menubar` | Top navigation | - |
| `navigation-menu` | Main navigation | Active states |
| `popover` | Tooltips, info panels | - |
| `progress` | Loading indicators | Custom colors |
| `radio-group` | Selection inputs | - |
| `scroll-area` | Custom scrollbars | - |
| `select` | Dropdown selects | - |
| `separator` | Visual dividers | - |
| `sheet` | Side panels, drawers | Slide animations |
| `skeleton` | Loading placeholders | - |
| `slider` | Range inputs | - |
| `switch` | Toggle inputs | Theme toggle |
| `table` | Data tables | Sortable, filterable |
| `tabs` | Content tabs | Animated transitions |
| `textarea` | Multi-line inputs | - |
| `toast` | Notifications | - |
| `toggle` | Binary switches | - |
| `tooltip` | Hover information | - |

### 2.2 Custom Components

#### Layout Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `Navbar` | `components/layout/Navbar.tsx` | Top navigation with logo, links, user menu |
| `Footer` | `components/layout/Footer.tsx` | Site footer with links, copyright |
| `Sidebar` | `components/layout/Sidebar.tsx` | Dashboard sidebar navigation |
| `PageContainer` | `components/layout/PageContainer.tsx` | Consistent page padding, max-width |
| `Breadcrumbs` | `components/layout/Breadcrumbs.tsx` | Navigation breadcrumbs |

#### Dashboard Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `AnimatedGauge` | `components/dashboard/AnimatedGauge.tsx` | Score display with animated needle |
| `ModuleCard` | `components/dashboard/ModuleCard.tsx` | 7 module cards with hover effects |
| `ScoreOverview` | `components/dashboard/ScoreOverview.tsx` | Overall score summary section |
| `TrendPreview` | `components/dashboard/TrendPreview.tsx` | Mini chart previews |
| `LastUpdated` | `components/dashboard/LastUpdated.tsx` | Data freshness indicator |

#### Chart Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `TrendChart` | `components/charts/TrendChart.tsx` | Historical data line/area chart |
| `BarChart` | `components/charts/BarChart.tsx` | Comparative bar chart |
| `GaugeChart` | `components/charts/GaugeChart.tsx` | Circular gauge visualization |
| `Sparkline` | `components/charts/Sparkline.tsx` | Mini trend indicator |
| `ChartTooltip` | `components/charts/ChartTooltip.tsx` | Custom chart tooltip |

#### Module Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `FactorTable` | `components/modules/FactorTable.tsx` | Sortable, filterable data table |
| `ScoreBadge` | `components/modules/ScoreBadge.tsx` | Color-coded score display |
| `TrendIndicator` | `components/modules/TrendIndicator.tsx` | Up/down trend arrows |
| `ModuleHeader` | `components/modules/ModuleHeader.tsx` | Module title, score, description |
| `DataPointCard` | `components/modules/DataPointCard.tsx` | Individual indicator card |

#### Landing Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `HeroSection` | `components/landing/HeroSection.tsx` | Main hero with gauge |
| `FeatureGrid` | `components/landing/FeatureGrid.tsx` | Feature cards grid |
| `ModulePreview` | `components/landing/ModulePreview.tsx` | Module showcase section |
| `TestimonialSection` | `components/landing/TestimonialSection.tsx` | User testimonials |
| `CTASection` | `components/landing/CTASection.tsx` | Call-to-action section |

#### Shared Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `ThemeToggle` | `components/shared/ThemeToggle.tsx` | Light/dark mode switch |
| `LanguageSwitcher` | `components/shared/LanguageSwitcher.tsx` | i18n language selector |
| `LoadingSpinner` | `components/shared/LoadingSpinner.tsx` | Loading state indicator |
| `ErrorBoundary` | `components/shared/ErrorBoundary.tsx` | Error catching |
| `ExportButton` | `components/shared/ExportButton.tsx` | Export dropdown (PDF/Excel/CSV) |
| `DateRangePicker` | `components/shared/DateRangePicker.tsx` | Date range selection |
| `SearchInput` | `components/shared/SearchInput.tsx` | Global search |
| `DataTable` | `components/shared/DataTable.tsx` | Reusable sortable table |

### 2.3 Third-Party Components

| Component | Source | Purpose |
|-----------|--------|---------|
| `ResponsiveGridLayout` | react-grid-layout | Draggable dashboard grid |
| `LineChart/AreaChart/BarChart` | Recharts | Data visualization |
| `motion.div` | Framer Motion | Animated containers |
| `AnimatePresence` | Framer Motion | Exit animations |

---

## 3. Animation Implementation Table

### 3.1 Animation Specifications

| Animation | Library | Implementation | Timing | Easing | Complexity |
|-----------|---------|----------------|--------|--------|------------|
| **Page Load - Staggered Fade** | Framer Motion | `staggerChildren: 0.1` on container, `opacity: 0→1` on children | 0.5s total | `easeOut` | Medium |
| **Scroll Reveal - Slide Up** | Framer Motion | `whileInView` with `y: 30→0`, `opacity: 0→1` | 0.6s | `cubic-bezier(0.16, 1, 0.3, 1)` | Medium |
| **Gauge Needle** | Framer Motion | `animate` with spring physics on rotation | Dynamic | `stiffness: 100, damping: 15` | High |
| **Card Hover** | CSS + Framer | `whileHover={{ y: -4 }}` + shadow transition | 0.2s | `ease` | Low |
| **Counter Animation** | Custom Hook | `useAnimatedCounter` with requestAnimationFrame | 1.5s | `easeOutExpo` | Medium |
| **Tab Transitions** | Framer Motion | `AnimatePresence` with fade + slide | 0.3s | `easeInOut` | Medium |
| **Button Hover** | CSS | `transform: scale(1.02)` + shadow | 0.15s | `ease` | Low |
| **Modal Open/Close** | Framer Motion | `AnimatePresence` with scale + fade | 0.25s | `spring` | Medium |
| **Sidebar Slide** | Framer Motion | `x: -100%→0` with `AnimatePresence` | 0.3s | `cubic-bezier(0.16, 1, 0.3, 1)` | Medium |
| **Toast Notification** | Framer Motion | Slide in from right + fade | 0.4s | `spring` | Low |
| **Chart Data Load** | Recharts | Animated line drawing | 1s | `easeOut` | Medium |
| **Skeleton Shimmer** | CSS | Shimmer gradient animation | 1.5s | `linear` | Low |
| **Dropdown Menu** | Framer Motion | Scale + fade from origin | 0.15s | `easeOut` | Low |
| **Theme Toggle** | Framer Motion | Rotate + scale icon swap | 0.3s | `spring` | Low |
| **Score Color Transition** | CSS | Background color interpolation | 0.5s | `ease` | Low |

### 3.2 Animation Component Mapping

| Component | Animations Applied |
|-----------|-------------------|
| `AnimatedGauge` | Needle spring rotation, counter animation, color transition |
| `ModuleCard` | Hover lift, staggered load, icon pulse |
| `TrendChart` | Line draw animation, tooltip fade, data point scale |
| `FactorTable` | Row stagger on load, hover highlight, sort transition |
| `ScoreBadge` | Color transition, pulse on update |
| `ThemeToggle` | Icon rotation, background slide |
| `LanguageSwitcher` | Dropdown slide, flag fade |
| `PageContainer` | Scroll reveal on sections |
| `Navbar` | Scroll hide/show, link hover underline |
| `HeroSection` | Staggered text reveal, gauge entrance |

---

## 4. Animation Library Choices

### 4.1 Primary: Framer Motion

**Rationale:**
- Declarative API perfect for React component-based architecture
- Built-in gesture support (hover, tap, drag)
- AnimatePresence for exit animations
- Spring physics for natural motion
- Layout animations for smooth transitions
- Excellent TypeScript support

**Use Cases:**
- Page transitions
- Scroll-triggered animations
- Complex gesture interactions
- Spring-based animations (gauge needle)
- Layout animations

**Configuration:**
```typescript
// Default transition settings
const defaultTransition = {
  type: "spring",
  stiffness: 100,
  damping: 15,
};

// Scroll reveal variant
const scrollReveal = {
  hidden: { opacity: 0, y: 30 },
  visible: { 
    opacity: 1, 
    y: 0,
    transition: {
      duration: 0.6,
      ease: [0.16, 1, 0.3, 1] // Custom cubic-bezier
    }
  }
};

// Stagger container
const staggerContainer = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1,
      delayChildren: 0.2
    }
  }
};
```

### 4.2 Secondary: CSS Animations

**Rationale:**
- Zero JavaScript overhead for simple effects
- GPU-accelerated transforms
- Perfect for micro-interactions
- Better performance for frequent triggers

**Use Cases:**
- Button hover states
- Link underlines
- Skeleton loading shimmer
- Simple opacity transitions
- Color transitions

**Configuration:**
```css
/* Card hover effect */
.card-hover {
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.card-hover:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 24px rgba(0, 0, 0, 0.15);
}

/* Skeleton shimmer */
@keyframes shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
.skeleton {
  background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite linear;
}
```

### 4.3 Custom Hooks

**useAnimatedCounter**
```typescript
// hooks/useAnimatedCounter.ts
export function useAnimatedCounter(
  end: number, 
  duration: number = 1500,
  start: number = 0
) {
  const [count, setCount] = useState(start);
  
  useEffect(() => {
    let startTime: number;
    let animationFrame: number;
    
    const animate = (timestamp: number) => {
      if (!startTime) startTime = timestamp;
      const progress = Math.min((timestamp - startTime) / duration, 1);
      
      // easeOutExpo easing
      const easeOutExpo = progress === 1 ? 1 : 1 - Math.pow(2, -10 * progress);
      
      setCount(Math.floor(start + (end - start) * easeOutExpo));
      
      if (progress < 1) {
        animationFrame = requestAnimationFrame(animate);
      }
    };
    
    animationFrame = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animationFrame);
  }, [end, duration, start]);
  
  return count;
}
```

**useScrollReveal**
```typescript
// hooks/useScrollReveal.ts
export function useScrollReveal() {
  return {
    initial: { opacity: 0, y: 30 },
    whileInView: { opacity: 1, y: 0 },
    viewport: { once: true, margin: "-100px" },
    transition: {
      duration: 0.6,
      ease: [0.16, 1, 0.3, 1]
    }
  };
}
```

---

## 5. Project File Structure

```
the-dial/
├── app/
│   ├── page.tsx                    # Landing page
│   ├── layout.tsx                  # Root layout with providers
│   ├── globals.css                 # Global styles, Tailwind
│   ├── loading.tsx                 # Global loading state
│   ├── error.tsx                   # Global error boundary
│   │
│   ├── dashboard/
│   │   ├── page.tsx                # Main dashboard
│   │   ├── layout.tsx              # Dashboard layout
│   │   └── loading.tsx             # Dashboard loading
│   │
│   ├── module/
│   │   └── [id]/
│   │       ├── page.tsx            # Module detail page
│   │       └── layout.tsx          # Module layout
│   │
│   ├── login/
│   │   └── page.tsx                # Login page
│   │
│   ├── signup/
│   │   └── page.tsx                # Signup page
│   │
│   ├── profile/
│   │   └── page.tsx                # User profile
│   │
│   ├── encyclopedia/
│   │   └── page.tsx                # Economic terms encyclopedia
│   │
│   ├── calendar/
│   │   └── page.tsx                # Economic calendar
│   │
│   ├── terms/
│   │   └── page.tsx                # Terms of service
│   │
│   ├── privacy/
│   │   └── page.tsx                # Privacy policy
│   │
│   ├── disclaimer/
│   │   └── page.tsx                # Disclaimer
│   │
│   └── api/
│       ├── auth/
│       │   ├── [...nextauth]/
│       │   │   └── route.ts        # NextAuth configuration
│       │   ├── login/
│       │   │   └── route.ts        # Login endpoint
│       │   ├── signup/
│       │   │   └── route.ts        # Signup endpoint
│       │   └── logout/
│       │       └── route.ts        # Logout endpoint
│       │
│       ├── fred/
│       │   ├── series/
│       │   │   └── route.ts        # FRED series data
│       │   ├── search/
│       │   │   └── route.ts        # FRED search
│       │   └── update/
│       │       └── route.ts        # Data update trigger
│       │
│       ├── scores/
│       │   ├── overall/
│       │   │   └── route.ts        # Overall score calculation
│       │   ├── module/
│       │   │   └── route.ts        # Module scores
│       │   └── history/
│       │       └── route.ts        # Score history
│       │
│       └── export/
│           ├── pdf/
│           │   └── route.ts        # PDF export
│           ├── excel/
│           │   └── route.ts        # Excel export
│           └── csv/
│               └── route.ts        # CSV export
│
├── components/
│   ├── ui/                         # shadcn/ui components
│   │   ├── accordion.tsx
│   │   ├── alert.tsx
│   │   ├── alert-dialog.tsx
│   │   ├── avatar.tsx
│   │   ├── badge.tsx
│   │   ├── button.tsx
│   │   ├── card.tsx
│   │   ├── checkbox.tsx
│   │   ├── collapsible.tsx
│   │   ├── command.tsx
│   │   ├── dialog.tsx
│   │   ├── dropdown-menu.tsx
│   │   ├── form.tsx
│   │   ├── input.tsx
│   │   ├── label.tsx
│   │   ├── menubar.tsx
│   │   ├── navigation-menu.tsx
│   │   ├── popover.tsx
│   │   ├── progress.tsx
│   │   ├── radio-group.tsx
│   │   ├── scroll-area.tsx
│   │   ├── select.tsx
│   │   ├── separator.tsx
│   │   ├── sheet.tsx
│   │   ├── skeleton.tsx
│   │   ├── slider.tsx
│   │   ├── switch.tsx
│   │   ├── table.tsx
│   │   ├── tabs.tsx
│   │   ├── textarea.tsx
│   │   ├── toast.tsx
│   │   ├── toaster.tsx
│   │   ├── toggle.tsx
│   │   └── tooltip.tsx
│   │
│   ├── layout/                     # Layout components
│   │   ├── Navbar.tsx
│   │   ├── Footer.tsx
│   │   ├── Sidebar.tsx
│   │   ├── PageContainer.tsx
│   │   └── Breadcrumbs.tsx
│   │
│   ├── dashboard/                  # Dashboard components
│   │   ├── AnimatedGauge.tsx
│   │   ├── ModuleCard.tsx
│   │   ├── ScoreOverview.tsx
│   │   ├── TrendPreview.tsx
│   │   └── LastUpdated.tsx
│   │
│   ├── charts/                     # Chart components
│   │   ├── TrendChart.tsx
│   │   ├── BarChart.tsx
│   │   ├── GaugeChart.tsx
│   │   ├── Sparkline.tsx
│   │   └── ChartTooltip.tsx
│   │
│   ├── modules/                    # Module components
│   │   ├── FactorTable.tsx
│   │   ├── ScoreBadge.tsx
│   │   ├── TrendIndicator.tsx
│   │   ├── ModuleHeader.tsx
│   │   └── DataPointCard.tsx
│   │
│   ├── landing/                    # Landing page components
│   │   ├── HeroSection.tsx
│   │   ├── FeatureGrid.tsx
│   │   ├── ModulePreview.tsx
│   │   ├── TestimonialSection.tsx
│   │   └── CTASection.tsx
│   │
│   └── shared/                     # Shared components
│       ├── ThemeToggle.tsx
│       ├── LanguageSwitcher.tsx
│       ├── LoadingSpinner.tsx
│       ├── ErrorBoundary.tsx
│       ├── ExportButton.tsx
│       ├── DateRangePicker.tsx
│       ├── SearchInput.tsx
│       └── DataTable.tsx
│
├── hooks/                          # Custom React hooks
│   ├── useFREDData.ts
│   ├── useScores.ts
│   ├── useAuth.ts
│   ├── useTheme.ts
│   ├── useAnimation.ts
│   ├── useAnimatedCounter.ts
│   ├── useScrollReveal.ts
│   ├── useLocalStorage.ts
│   └── useDebounce.ts
│
├── lib/                            # Utility libraries
│   ├── utils.ts                    # General utilities
│   ├── fred-api.ts                 # FRED API client
│   ├── scoring.ts                  # Score calculation logic
│   ├── export.ts                   # Export utilities
│   ├── i18n.ts                     # Internationalization config
│   ├── animations.ts               # Animation variants
│   └── constants.ts                # App constants
│
├── types/                          # TypeScript types
│   ├── index.ts                    # Common types
│   ├── fred.ts                     # FRED API types
│   ├── modules.ts                  # Module types
│   ├── scores.ts                   # Score types
│   ├── user.ts                     # User types
│   └── api.ts                      # API types
│
├── public/                         # Static assets
│   ├── images/
│   │   ├── logo.svg
│   │   ├── logo-dark.svg
│   │   ├── hero-bg.jpg
│   │   └── icons/
│   └── locales/
│       ├── en/
│       │   └── common.json
│       ├── zh/
│       │   └── common.json
│       └── ja/
│           └── common.json
│
├── prisma/                         # Database (future)
│   └── schema.prisma
│
├── scripts/                        # Build/utility scripts
│   └── update-fred-data.ts
│
├── tests/                          # Test files
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── .env.local                      # Environment variables
├── .env.example                    # Environment template
├── next.config.js                  # Next.js config
├── tailwind.config.ts              # Tailwind config
├── tsconfig.json                   # TypeScript config
├── components.json                 # shadcn config
└── package.json
```

---

## 6. Package Installation List

### 6.1 Core Dependencies

```bash
# Framework & Core
npm install next@14 react@18 react-dom@18

# TypeScript
npm install -D typescript@5 @types/react @types/node

# Styling
npm install -D tailwindcss@3.4 postcss autoprefixer
npx tailwindcss init -p

# shadcn/ui
npx shadcn-ui@latest init
```

### 6.2 shadcn/ui Components

```bash
# Install all required shadcn components
npx shadcn-ui@latest add accordion
npx shadcn-ui@latest add alert
npx shadcn-ui@latest add alert-dialog
npx shadcn-ui@latest add avatar
npx shadcn-ui@latest add badge
npx shadcn-ui@latest add button
npx shadcn-ui@latest add card
npx shadcn-ui@latest add checkbox
npx shadcn-ui@latest add collapsible
npx shadcn-ui@latest add command
npx shadcn-ui@latest add dialog
npx shadcn-ui@latest add dropdown-menu
npx shadcn-ui@latest add form
npx shadcn-ui@latest add input
npx shadcn-ui@latest add label
npx shadcn-ui@latest add menubar
npx shadcn-ui@latest add navigation-menu
npx shadcn-ui@latest add popover
npx shadcn-ui@latest add progress
npx shadcn-ui@latest add radio-group
npx shadcn-ui@latest add scroll-area
npx shadcn-ui@latest add select
npx shadcn-ui@latest add separator
npx shadcn-ui@latest add sheet
npx shadcn-ui@latest add skeleton
npx shadcn-ui@latest add slider
npx shadcn-ui@latest add switch
npx shadcn-ui@latest add table
npx shadcn-ui@latest add tabs
npx shadcn-ui@latest add textarea
npx shadcn-ui@latest add toast
npx shadcn-ui@latest add toggle
npx shadcn-ui@latest add tooltip
```

### 6.3 Animation Libraries

```bash
# Primary animation library
npm install framer-motion
```

### 6.4 Data Visualization

```bash
# Charts
npm install recharts

# Dashboard grid
npm install react-grid-layout
npm install -D @types/react-grid-layout
```

### 6.5 State Management

```bash
# Server state
npm install @tanstack/react-query

# Client state
npm install zustand

# Form handling
npm install react-hook-form

# Validation
npm install zod
npm install @hookform/resolvers
```

### 6.6 Data Integration

```bash
# HTTP client
npm install axios

# Date handling
npm install date-fns
```

### 6.7 Export Functionality

```bash
# PDF generation
npm install jspdf
npm install html2canvas

# Excel export
npm install xlsx
```

### 6.8 Authentication & Theming

```bash
# Authentication
npm install next-auth

# Theming
npm install next-themes

# Internationalization
npm install next-intl
```

### 6.9 Icons & Utilities

```bash
# Icons
npm install lucide-react

# Utilities (usually included with shadcn)
npm install clsx tailwind-merge
npm install class-variance-authority
```

### 6.10 Development Dependencies

```bash
# Linting & Formatting
npm install -D eslint eslint-config-next prettier

# Testing (optional)
npm install -D jest @testing-library/react @testing-library/jest-dom

# Type definitions
npm install -D @types/jspdf
```

### 6.11 Complete Package.json Dependencies

```json
{
  "dependencies": {
    "@hookform/resolvers": "^3.3.4",
    "@radix-ui/react-accordion": "^1.1.2",
    "@radix-ui/react-alert-dialog": "^1.0.5",
    "@radix-ui/react-avatar": "^1.0.4",
    "@radix-ui/react-checkbox": "^1.0.4",
    "@radix-ui/react-collapsible": "^1.0.3",
    "@radix-ui/react-dialog": "^1.0.5",
    "@radix-ui/react-dropdown-menu": "^2.0.6",
    "@radix-ui/react-label": "^2.0.2",
    "@radix-ui/react-menubar": "^1.0.4",
    "@radix-ui/react-navigation-menu": "^1.1.4",
    "@radix-ui/react-popover": "^1.0.7",
    "@radix-ui/react-progress": "^1.0.3",
    "@radix-ui/react-radio-group": "^1.1.3",
    "@radix-ui/react-scroll-area": "^1.0.5",
    "@radix-ui/react-select": "^2.0.0",
    "@radix-ui/react-separator": "^1.0.3",
    "@radix-ui/react-slider": "^1.1.2",
    "@radix-ui/react-slot": "^1.0.2",
    "@radix-ui/react-switch": "^1.0.3",
    "@radix-ui/react-tabs": "^1.0.4",
    "@radix-ui/react-toast": "^1.1.5",
    "@radix-ui/react-toggle": "^1.0.3",
    "@radix-ui/react-tooltip": "^1.0.7",
    "@tanstack/react-query": "^5.17.0",
    "axios": "^1.6.5",
    "class-variance-authority": "^0.7.0",
    "clsx": "^2.1.0",
    "cmdk": "^0.2.0",
    "date-fns": "^3.2.0",
    "framer-motion": "^10.18.0",
    "html2canvas": "^1.4.1",
    "jspdf": "^2.5.1",
    "lucide-react": "^0.312.0",
    "next": "14.0.4",
    "next-auth": "^4.24.5",
    "next-intl": "^3.4.2",
    "next-themes": "^0.2.1",
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-grid-layout": "^1.4.4",
    "react-hook-form": "^7.49.3",
    "recharts": "^2.10.4",
    "tailwind-merge": "^2.2.0",
    "tailwindcss-animate": "^1.0.7",
    "xlsx": "^0.18.5",
    "zod": "^3.22.4",
    "zustand": "^4.4.7"
  },
  "devDependencies": {
    "@types/node": "^20.11.0",
    "@types/react": "^18.2.47",
    "@types/react-dom": "^18.2.18",
    "@types/react-grid-layout": "^1.3.5",
    "autoprefixer": "^10.4.16",
    "eslint": "^8.56.0",
    "eslint-config-next": "14.0.4",
    "postcss": "^8.4.33",
    "prettier": "^3.2.2",
    "tailwindcss": "^3.4.1",
    "typescript": "^5.3.3"
  }
}
```

---

## 7. Environment Configuration

### 7.1 Required Environment Variables

```bash
# .env.local

# App
NEXT_PUBLIC_APP_NAME="The Dial"
NEXT_PUBLIC_APP_URL=http://localhost:3000

# FRED API
FRED_API_KEY=your_fred_api_key_here
FRED_API_URL=https://api.stlouisfed.org/fred

# Authentication
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=your_nextauth_secret_here

# Database (future)
# DATABASE_URL=postgresql://user:password@localhost:5432/thedial

# Redis (future)
# REDIS_URL=redis://localhost:6379
```

---

## 8. API Integration

### 8.1 FRED API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/fred/series` | GET | Fetch economic series data |
| `/api/fred/search` | GET | Search FRED database |
| `/api/fred/update` | POST | Trigger data update |

### 8.2 Score Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/scores/overall` | GET | Get overall economic score |
| `/api/scores/module` | GET | Get module-specific scores |
| `/api/scores/history` | GET | Get score history |

### 8.3 Export Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/export/pdf` | POST | Generate PDF report |
| `/api/export/excel` | POST | Generate Excel file |
| `/api/export/csv` | POST | Generate CSV file |

---

## 9. Performance Considerations

### 9.1 Optimization Strategies

| Strategy | Implementation |
|----------|----------------|
| **Code Splitting** | Dynamic imports for heavy components |
| **Image Optimization** | Next.js Image component with WebP |
| **Data Caching** | React Query with 5-minute stale time |
| **Animation Performance** | `will-change` on animated elements |
| **Bundle Size** | Tree-shaking, selective imports |
| **Lazy Loading** | Intersection Observer for below-fold content |

### 9.2 Animation Performance

```typescript
// Use transform and opacity only
const performantAnimation = {
  transform: "translateY(0)",
  opacity: 1
};

// Add will-change hint
const animatedElement = {
  willChange: "transform, opacity"
};

// Use reduced motion preference
const prefersReducedMotion = 
  typeof window !== 'undefined' && 
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;
```

---

## 10. Security Considerations

| Concern | Mitigation |
|---------|------------|
| API Key Exposure | Server-side only, env variables |
| XSS | React escaping, input sanitization |
| CSRF | NextAuth.js built-in protection |
| Rate Limiting | API route middleware |
| Data Validation | Zod schemas on all inputs |

---

## 11. Development Workflow

### 11.1 Setup Commands

```bash
# 1. Create project
npx create-next-app@14 the-dial --typescript --tailwind --app

# 2. Initialize shadcn
npx shadcn-ui@latest init

# 3. Install all dependencies
npm install framer-motion recharts @tanstack/react-query zustand ...

# 4. Install shadcn components
npx shadcn-ui@latest add button card badge ...

# 5. Run development server
npm run dev
```

### 11.2 Build & Deploy

```bash
# Build for production
npm run build

# Start production server
npm start

# Lint check
npm run lint
```

---

## Appendix: Key Implementation Notes

### Gauge Animation Detail

The gauge needle uses Framer Motion's spring physics for natural movement:

```typescript
<motion.div
  className="gauge-needle"
  animate={{ rotate: scoreToAngle(score) }}
  transition={{
    type: "spring",
    stiffness: 100,
    damping: 15,
    mass: 1
  }}
/>
```

### Counter Animation Detail

The counter uses `requestAnimationFrame` with easing:

```typescript
// easeOutExpo for natural deceleration
const easeOutExpo = (t: number) => 
  t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
```

### Scroll Reveal Detail

Uses Framer Motion's `whileInView` with custom cubic-bezier:

```typescript
// Custom easing for premium feel
const customEase = [0.16, 1, 0.3, 1]; // cubic-bezier
```

---

*Document Version: 1.0.0*
*Last Updated: 2024*
*Author: Technical Specification Generator*
