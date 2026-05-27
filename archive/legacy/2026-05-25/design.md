# The Dial - Design Document

## 1. Overview

### Project Summary
**The Dial** is a professional macroeconomic research dashboard platform that aggregates 47 macroeconomic factors across 7 analysis modules to provide a comprehensive view of economic conditions. The platform features a proprietary scoring system (0-100) that contextualizes current economic data against historical percentiles, making complex macroeconomic analysis accessible to researchers, policy analysts, and macro enthusiasts.

The platform combines real-time data from FRED (Federal Reserve Economic Data) API with elegant visualizations including animated gauges, historical trend charts, and interactive module cards. Users can track liquidity conditions, funding markets, treasury dynamics, interest rates, credit spreads, risk indicators, and external factors through an intuitive dashboard interface.

### Target Audience
- **Primary:** Economics Researchers and Policy Analysts at financial institutions
- **Secondary:** Independent Analysts and Investment Professionals
- **Tertiary:** Macro Enthusiasts and Advanced Retail Investors

### Language Support
- Primary: English (en)
- Secondary: Chinese (zh) - planned for future release

---

## 2. Page Manifest

| Page ID | Page Name | File Name | Is Entry | Notes |
|---------|-----------|-----------|----------|-------|
| landing | Landing Page | index.html | Yes | Marketing page with hero, features, pricing |
| dashboard | Dashboard | dashboard.html | No | Main macroeconomic score dashboard |
| liquidity | Liquidity Module | modules/liquidity.html | No | 8 liquidity factors detail |
| funding | Funding Module | modules/funding.html | No | 12 funding factors detail |
| treasury | Treasury Module | modules/treasury.html | No | 8 treasury factors detail |
| rates | Rates Module | modules/rates.html | No | 5 rates factors detail |
| credit | Credit Module | modules/credit.html | No | 4 credit factors detail |
| risk | Risk Module | modules/risk.html | No | 5 risk factors detail |
| external | External Module | modules/external.html | No | 5 external factors detail |
| login | Login | auth/login.html | No | User authentication |
| signup | Sign Up | auth/signup.html | No | User registration |
| profile | User Profile | profile.html | No | User settings and preferences |
| calendar | Economic Calendar | calendar.html | No | Economic events and releases |
| encyclopedia | Encyclopedia | encyclopedia.html | No | Macroeconomic terms glossary |
| terms | Terms of Service | legal/terms.html | No | Legal terms |
| privacy | Privacy Policy | legal/privacy.html | No | Privacy policy |
| disclaimer | Disclaimer | legal/disclaimer.html | No | Data disclaimer |

---

## 3. Global Design System

### Color Palette

#### Light Mode
```css
--background: #fafafc;
--background-secondary: #f2f2f7;
--foreground: #3c3c43;
--foreground-secondary: #636366;
--foreground-muted: #8e8e93;
--card: #ffffff;
--card-secondary: #f2f2f7;
--border: #e5e5ea;
--border-subtle: #f2f2f7;
```

#### Dark Mode
```css
--background: #1c1c1e;
--background-secondary: #2c2c2e;
--foreground: #ffffff;
--foreground-secondary: #aeaeb2;
--foreground-muted: #636366;
--card: #2c2c2e;
--card-secondary: #3a3a3c;
--border: #38383a;
--border-subtle: #2c2c2e;
```

#### Score Colors (Universal)
```css
--score-green: #34c759;
--score-green-light: #30d158;
--score-yellow: #ff9500;
--score-orange: #ff9f0a;
--score-red: #ff3b30;
--score-red-dark: #ff453a;
```

#### Accent Colors
```css
--accent-primary: #007aff;
--accent-primary-hover: #0051d5;
--accent-secondary: #5856d6;
--accent-success: #34c759;
--accent-warning: #ff9500;
--accent-danger: #ff3b30;
```

#### Module Colors
```css
--liquidity: #007aff;
--funding: #5856d6;
--treasury: #af52de;
--rates: #ff2d55;
--credit: #ff9500;
--risk: #ff3b30;
--external: #34c759;
```

### Typography System

#### Font Families
```css
--font-primary: 'Inter', -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', Roboto, sans-serif;
--font-mono: 'IBM Plex Mono', 'SF Mono', 'Monaco', 'Inconsolata', monospace;
--font-display: 'SF Pro Display', 'Inter', -apple-system, sans-serif;
```

#### Type Scale
| Level | Size | Weight | Line Height | Letter Spacing | Usage |
|-------|------|--------|-------------|----------------|-------|
| H1 | 48px / 3rem | 700 | 1.1 | -0.02em | Hero headlines |
| H2 | 36px / 2.25rem | 600 | 1.2 | -0.01em | Section headers |
| H3 | 28px / 1.75rem | 600 | 1.3 | -0.01em | Card titles |
| H4 | 22px / 1.375rem | 600 | 1.4 | 0 | Subsection headers |
| H5 | 18px / 1.125rem | 600 | 1.5 | 0 | Component labels |
| H6 | 14px / 0.875rem | 600 | 1.5 | 0.01em | Small labels |
| Body | 16px / 1rem | 400 | 1.6 | 0 | Paragraph text |
| Body Small | 14px / 0.875rem | 400 | 1.5 | 0 | Secondary text |
| Caption | 12px / 0.75rem | 400 | 1.4 | 0.01em | Metadata, timestamps |
| Overline | 11px / 0.6875rem | 500 | 1.2 | 0.05em | Labels, badges |

### Spacing System
```css
--space-1: 4px;
--space-2: 8px;
--space-3: 12px;
--space-4: 16px;
--space-5: 20px;
--space-6: 24px;
--space-8: 32px;
--space-10: 40px;
--space-12: 48px;
--space-16: 64px;
--space-20: 80px;
--space-24: 96px;
```

### Border Radius
```css
--radius-sm: 6px;
--radius-md: 10px;
--radius-lg: 16px;
--radius-xl: 24px;
--radius-full: 9999px;
```

### Shadows
```css
/* Light Mode */
--shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.04);
--shadow-md: 0 4px 12px rgba(0, 0, 0, 0.08);
--shadow-lg: 0 12px 32px rgba(0, 0, 0, 0.12);
--shadow-xl: 0 24px 48px rgba(0, 0, 0, 0.16);

/* Dark Mode */
--shadow-dark-sm: 0 1px 2px rgba(0, 0, 0, 0.2);
--shadow-dark-md: 0 4px 12px rgba(0, 0, 0, 0.3);
--shadow-dark-lg: 0 12px 32px rgba(0, 0, 0, 0.4);
```

### Layout Specifications
```css
--header-height: 52px;
--max-content-width: 1200px;
--content-padding: 24px;
--sidebar-width: 280px;
--card-gap: 16px;
```

### Animation Specifications

#### Timing Functions
```css
--ease-out-expo: cubic-bezier(0.16, 1, 0.3, 1);
--ease-out-quart: cubic-bezier(0.25, 1, 0.5, 1);
--ease-out-back: cubic-bezier(0.34, 1.56, 0.64, 1);
--ease-in-out-quart: cubic-bezier(0.76, 0, 0.24, 1);
--ease-spring: cubic-bezier(0.175, 0.885, 0.32, 1.275);
```

#### Duration Standards
```css
--duration-fast: 150ms;
--duration-normal: 250ms;
--duration-slow: 400ms;
--duration-slower: 600ms;
--duration-gauge: 800ms;
```

#### Standard Animations

**Fade In Up (Scroll Reveal)**
```css
@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(24px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
/* Duration: 600ms, Easing: ease-out-expo */
```

**Stagger Children**
```css
/* Parent container */
.stagger-container > * {
  animation: fadeInUp 600ms var(--ease-out-expo) forwards;
  opacity: 0;
}
.stagger-container > *:nth-child(1) { animation-delay: 0ms; }
.stagger-container > *:nth-child(2) { animation-delay: 100ms; }
.stagger-container > *:nth-child(3) { animation-delay: 200ms; }
.stagger-container > *:nth-child(4) { animation-delay: 300ms; }
.stagger-container > *:nth-child(5) { animation-delay: 400ms; }
.stagger-container > *:nth-child(6) { animation-delay: 500ms; }
.stagger-container > *:nth-child(7) { animation-delay: 600ms; }
```

**Gauge Needle Animation**
```css
@keyframes gaugeNeedle {
  from {
    transform: rotate(-90deg);
  }
  to {
    transform: rotate(var(--needle-rotation));
  }
}
/* Duration: 800ms, Easing: ease-out-expo */
```

**Counter Animation**
```css
@keyframes countUp {
  from {
    --num: 0;
  }
}
/* Uses CSS counter with JS-driven progress */
/* Duration: 1200ms, Easing: ease-out-quart */
```

**Card Hover Lift**
```css
.card-hover {
  transition: transform 250ms var(--ease-out-quart),
              box-shadow 250ms var(--ease-out-quart);
}
.card-hover:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-lg);
}
```

**Pulse Animation (Live Indicator)**
```css
@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}
/* Duration: 2000ms, Infinite */
```

**Score Color Transition**
```css
.score-value {
  transition: color 400ms var(--ease-out-quart);
}
```

---

## 4. Page Specifications

### Page: Landing (index.html)

**Purpose:** Marketing and conversion page introducing The Dial platform

**Sections:**
1. Navigation Bar
2. Hero Section with Animated Gauge
3. Stats Counter Section
4. Feature Grid
5. Live Product Preview
6. Seven Module Cards
7. How It Works
8. Target Audience
9. Pricing Section
10. FAQ Section
11. Footer

**Layout:**
- Full-width sections with max-width content container (1200px)
- Single column layout with centered content
- Responsive: Stack to single column on mobile

**Components:**

**Navigation Bar**
- Height: 52px
- Background: transparent → blur on scroll
- Logo: Left-aligned, 32px height
- Links: Features, Pricing, How It Works (center)
- Actions: Theme toggle, Language switcher, Login button (right)
- Scroll behavior: Add backdrop-blur and border-bottom after 50px scroll

**Hero Section**
- Padding: 120px top, 80px bottom
- Headline: "Macroeconomic Intelligence, Simplified"
- Subheadline: "Track 47 macro factors across 7 modules. Get percentile-based context for every economic indicator."
- CTA Buttons: "Get Started Free" (primary), "View Dashboard" (secondary)
- Animated Gauge: 280px diameter, centered below text
- Gauge Animation: Needle rotates from -90deg to calculated position over 800ms with ease-out-expo

**Stats Counter Section**
- 4-column grid on desktop, 2x2 on tablet, single column on mobile
- Each stat: Large number (48px) with animated count-up
- Labels below in muted text
- Stats:
  - "47" - Macroeconomic Factors
  - "7" - Analysis Modules
  - "5Y" - Rolling Window
  - "Daily" - Data Updates

**Feature Grid**
- 2x3 grid on desktop, single column on mobile
- Each feature card:
  - Icon: 48px, module color
  - Title: H4
  - Description: Body text
  - Hover: translateY(-2px), shadow increase

**Live Product Preview**
- Full-width container with rounded corners (16px)
- Contains mini dashboard preview
- Theme toggle to switch between light/dark preview
- Border: 1px solid var(--border)

**Seven Module Cards**
- Horizontal scroll on mobile, grid on desktop
- Each card: 200px width
- Contains: Module icon, name, factor count, mini score indicator
- Colors per module (see Module Colors)

**How It Works**
- 3-step horizontal layout
- Each step: Number badge, title, description
- Connecting line between steps
- Icons: Database, Calculator, LayoutDashboard

**Target Audience**
- 4-column grid
- Each card: Avatar/icon, role title, description
- Cards: subtle background, rounded corners

**Pricing Section**
- 2-column layout (Free vs Pro)
- Free card: $0, basic features
- Pro card: $12.9/month, highlighted with accent border
- Feature checklist in each
- CTA buttons

**FAQ Section**
- Accordion-style expandable items
- Smooth height transition (300ms)
- Chevron rotation on expand

**Footer**
- 4-column grid: Product, Resources, Legal, Connect
- Copyright and social links
- Background: var(--background-secondary)

**Animations:**
- Page load: Staggered fade-in for all sections (100ms delay per element)
- Scroll reveal: Sections fade in up when entering viewport
- Stats: Count-up animation on scroll into view
- Gauge: Animated needle on page load
- Cards: Hover lift effect

---

### Page: Dashboard (dashboard.html)

**Purpose:** Main dashboard displaying overall macroeconomic conditions score

**Layout:**
- Header with navigation
- Main content: 2-column layout (left: score gauge, right: trend chart)
- Below: 7 module cards in grid
- Bottom: Factor distribution and top lift/drag factors

**Components:**

**Overall Score Section**
- Large gauge: 320px diameter
- Score display: 72px font, color-coded
- Status label: "Expansionary" / "Neutral" / "Contractionary"
- Last updated timestamp
- Historical percentile context

**Trend Chart**
- Line chart showing 5-year history
- Y-axis: Score 0-100
- X-axis: Time (monthly ticks)
- Gradient fill below line
- Hover tooltip with exact values
- Chart library: Recharts

**Module Cards Grid**
- 7 cards in responsive grid (4+3 or 3+2+2 layout)
- Each card:
  - Module icon and name
  - Current score with color indicator
  - Mini sparkline chart
  - Factor count
  - Click to navigate to module detail

**Factor Distribution**
- Horizontal bar chart
- Shows count of factors in each score range (0-30, 30-50, 50-70, 70-100)
- Color-coded segments

**Top Lift/Drag Factors**
- Two lists side by side
- Lift: Factors with highest positive contribution
- Drag: Factors with highest negative contribution
- Each item: Factor name, module, score, change indicator

**Animations:**
- Gauge needle: 800ms ease-out-expo rotation on load
- Cards: Staggered fade-in (100ms delay)
- Charts: Draw animation on load
- Numbers: Count-up animation

---

### Page: Liquidity Module (modules/liquidity.html)

**Purpose:** Detailed view of liquidity-related macroeconomic factors

**Layout:**
- Module header with score and description
- 8 factor cards in grid
- Each factor: Current value, percentile score, historical chart

**Factors (8):**
1. Net Liquidity
2. Bank Reserves
3. Liquidity Momentum
4. TGA Deviation
5. ON RRP Risk
6. Fed Balance Sheet
7. Reserve Balances
8. Currency in Circulation

**Components:**
- Module header: Icon, title, overall score, description
- Factor cards: Each with sparkline, current value, percentile, trend indicator
- Historical chart: Full module trend over 5 years
- Data table: All factors with sortable columns

**Animations:**
- Cards: Staggered fade-in on load
- Charts: Animated draw on scroll into view
- Score updates: Color transition 400ms

---

### Page: Funding Module (modules/funding.html)

**Purpose:** Detailed view of funding market conditions

**Factors (12):**
1. SOFR Rate
2. EFFR Rate
3. IOER Rate
4. Repo Rates
5. LIBOR Spread
6. FRA-OIS Spread
7. TED Spread
8. Commercial Paper Spread
9. Bank Funding Stress
10. MMF Flows
11. Primary Dealer Funding
12. Secured Funding Rate

**Layout & Components:** Same structure as Liquidity module

---

### Page: Treasury Module (modules/treasury.html)

**Purpose:** Treasury market dynamics and yield curve analysis

**Factors (8):**
1. Yield Curve Slope (10Y-2Y)
2. Yield Curve Slope (10Y-3M)
3. Term Premium
4. Treasury Volatility
5. Treasury Supply
6. Foreign Demand
7. Real Yields
8. Inflation Breakeven

**Layout & Components:** Same structure as Liquidity module

---

### Page: Rates Module (modules/rates.html)

**Purpose:** Interest rate environment analysis

**Factors (5):**
1. Fed Funds Rate
2. 10-Year Treasury Yield
3. 2-Year Treasury Yield
4. 30-Year Treasury Yield
5. Real Fed Funds Rate

**Layout & Components:** Same structure as Liquidity module

---

### Page: Credit Module (modules/credit.html)

**Purpose:** Credit market conditions and spreads

**Factors (4):**
1. IG Credit Spread
2. HY Credit Spread
3. CDS Index
4. Bond Market Liquidity

**Layout & Components:** Same structure as Liquidity module

---

### Page: Risk Module (modules/risk.html)

**Purpose:** Market risk indicators and volatility measures

**Factors (5):**
1. VIX Index
2. Equity Volatility
3. FX Volatility
4. Cross-Asset Correlation
5. Risk Appetite Index

**Layout & Components:** Same structure as Liquidity module

---

### Page: External Module (modules/external.html)

**Purpose:** External economic factors and global conditions

**Factors (5):**
1. Dollar Index (DXY)
2. Global PMI
3. Commodity Prices
4. Emerging Market Stress
5. Global Liquidity

**Layout & Components:** Same structure as Liquidity module

---

### Page: Login (auth/login.html)

**Purpose:** User authentication

**Layout:**
- Centered card (400px max-width)
- Logo at top
- Email/password inputs
- Social login options
- Link to signup

**Components:**
- Email input with validation
- Password input with visibility toggle
- "Remember me" checkbox
- Submit button with loading state
- Google/GitHub OAuth buttons
- "Forgot password" link

**Animations:**
- Card: Fade in up on load
- Input focus: Border color transition 200ms
- Button hover: Scale 1.02, shadow increase
- Error shake: 300ms horizontal shake

---

### Page: Sign Up (auth/signup.html)

**Purpose:** User registration

**Layout:**
- Similar to login
- Additional fields: Name, confirm password
- Terms acceptance checkbox

**Components:**
- Full name input
- Email input
- Password input with strength indicator
- Confirm password input
- Terms checkbox
- Submit button

**Animations:** Same as Login

---

### Page: Profile (profile.html)

**Purpose:** User settings and preferences

**Layout:**
- Sidebar navigation (Settings, Notifications, Billing, API)
- Main content area with forms

**Components:**
- Profile information form
- Theme preference selector
- Notification preferences
- API key management
- Subscription status

---

### Page: Economic Calendar (calendar.html)

**Purpose:** Display upcoming economic data releases

**Layout:**
- Calendar grid view
- List of events with filters
- Impact indicators (high/medium/low)

**Components:**
- Date picker
- Country/region filter
- Impact level filter
- Event cards with forecast vs actual
- Alert settings

---

### Page: Encyclopedia (encyclopedia.html)

**Purpose:** Macroeconomic terms glossary

**Layout:**
- Search bar at top
- Alphabetical navigation
- Term cards with definitions

**Components:**
- Search input with autocomplete
- A-Z quick navigation
- Term cards: Title, definition, related terms
- Category filters

---

### Legal Pages (terms.html, privacy.html, disclaimer.html)

**Purpose:** Legal documentation

**Layout:**
- Simple text layout
- Table of contents sidebar
- Main content area

**Components:**
- Section navigation
- Last updated date
- Print-friendly styling

---

## 5. Technical Requirements

### CDN Dependencies
```html
<!-- React & ReactDOM -->
<script src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
<script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>

<!-- Tailwind CSS -->
<script src="https://cdn.tailwindcss.com"></script>

<!-- Lucide Icons -->
<script src="https://unpkg.com/lucide@latest"></script>

<!-- Recharts (for dashboard pages) -->
<script src="https://unpkg.com/recharts/umd/Recharts.min.js"></script>

<!-- Date-fns -->
<script src="https://unpkg.com/date-fns@2.29.3/index.umd.min.js"></script>
```

### Build Configuration (Tailwind)
```javascript
// tailwind.config.js
module.exports = {
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        background: {
          DEFAULT: 'var(--background)',
          secondary: 'var(--background-secondary)',
        },
        foreground: {
          DEFAULT: 'var(--foreground)',
          secondary: 'var(--foreground-secondary)',
          muted: 'var(--foreground-muted)',
        },
        card: {
          DEFAULT: 'var(--card)',
          secondary: 'var(--card-secondary)',
        },
        border: {
          DEFAULT: 'var(--border)',
          subtle: 'var(--border-subtle)',
        },
        score: {
          green: '#34c759',
          yellow: '#ff9500',
          red: '#ff3b30',
        },
        accent: {
          primary: '#007aff',
          secondary: '#5856d6',
        },
        module: {
          liquidity: '#007aff',
          funding: '#5856d6',
          treasury: '#af52de',
          rates: '#ff2d55',
          credit: '#ff9500',
          risk: '#ff3b30',
          external: '#34c759',
        },
      },
      fontFamily: {
        sans: ['Inter', 'SF Pro Display', 'system-ui', 'sans-serif'],
        mono: ['IBM Plex Mono', 'SF Mono', 'monospace'],
      },
      spacing: {
        '13': '3.25rem',
        '15': '3.75rem',
        '18': '4.5rem',
      },
      borderRadius: {
        'md': '10px',
        'lg': '16px',
        'xl': '24px',
      },
      boxShadow: {
        'card': '0 4px 12px rgba(0, 0, 0, 0.08)',
        'card-hover': '0 12px 32px rgba(0, 0, 0, 0.12)',
        'dark-card': '0 4px 12px rgba(0, 0, 0, 0.3)',
      },
      animation: {
        'fade-in-up': 'fadeInUp 600ms cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'gauge-needle': 'gaugeNeedle 800ms cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'pulse-slow': 'pulse 2s ease-in-out infinite',
        'count-up': 'countUp 1200ms cubic-bezier(0.25, 1, 0.5, 1) forwards',
      },
      keyframes: {
        fadeInUp: {
          '0%': { opacity: '0', transform: 'translateY(24px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        gaugeNeedle: {
          '0%': { transform: 'rotate(-90deg)' },
          '100%': { transform: 'rotate(var(--needle-rotation))' },
        },
        countUp: {
          '0%': { '--num': '0' },
          '100%': { '--num': 'var(--target-num)' },
        },
      },
    },
  },
  plugins: [],
}
```

### Browser Support
- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

### Performance Targets
- First Contentful Paint: < 1.5s
- Largest Contentful Paint: < 2.5s
- Time to Interactive: < 3.5s
- Cumulative Layout Shift: < 0.1

---

## 6. Image Requirements

### Logo & Branding
| Image Name | Description | Search Keywords / Generation Prompt |
|------------|-------------|-------------------------------------|
| logo-dark.svg | Dark mode logo | "The Dial" text logo, modern sans-serif, white on transparent |
| logo-light.svg | Light mode logo | "The Dial" text logo, modern sans-serif, dark on transparent |
| favicon.ico | Site favicon | Gauge dial icon, minimalist |
| og-image.jpg | Social preview | "The Dial macroeconomic dashboard preview, professional financial interface with gauge visualization, blue and white color scheme, modern UI design, 1200x630px" |

### Hero & Marketing
| Image Name | Description | Search Keywords / Generation Prompt |
|------------|-------------|-------------------------------------|
| hero-illustration.svg | Hero section illustration | Abstract gauge visualization, flowing data lines, modern fintech aesthetic, blue gradient |
| dashboard-preview-light.jpg | Dashboard screenshot (light) | "Professional financial dashboard interface, clean white background, data visualization charts, modern UI, light theme" |
| dashboard-preview-dark.jpg | Dashboard screenshot (dark) | "Professional financial dashboard interface, dark background, data visualization charts, modern UI, dark theme" |

### Module Icons (SVG)
| Icon Name | Description | Color |
|-----------|-------------|-------|
| icon-liquidity.svg | Water/droplet flow icon | #007aff |
| icon-funding.svg | Bank/building icon | #5856d6 |
| icon-treasury.svg | Government/building icon | #af52de |
| icon-rates.svg | Percentage/chart icon | #ff2d55 |
| icon-credit.svg | Credit card/document icon | #ff9500 |
| icon-risk.svg | Warning/alert icon | #ff3b30 |
| icon-external.svg | Globe/world icon | #34c759 |

### Audience Avatars
| Image Name | Description | Search Keywords / Generation Prompt |
|------------|-------------|-------------------------------------|
| avatar-researcher.jpg | Economics researcher | "Professional economist portrait, office setting, neutral background, business attire" |
| avatar-analyst.jpg | Policy analyst | "Government policy analyst portrait, professional setting, neutral background" |
| avatar-independent.jpg | Independent analyst | "Independent financial analyst portrait, modern office, professional attire" |
| avatar-enthusiast.jpg | Macro enthusiast | "Young professional interested in economics, casual business attire, friendly expression" |

### Background Patterns
| Image Name | Description | Search Keywords / Generation Prompt |
|------------|-------------|-------------------------------------|
| pattern-grid.svg | Subtle grid pattern | Minimalist dot grid, very light gray, 20px spacing |
| pattern-dots.svg | Dot pattern overlay | Subtle dots, low opacity, decorative |

---

## 7. Navigation Structure

### Header Navigation
```
[Logo]                    [Features] [Pricing] [How It Works]                    [Theme Toggle] [Language] [Login]
```

### Footer Navigation
```
Product                    Resources                    Legal                    Connect
- Dashboard                - Encyclopedia               - Terms of Service       - Twitter
- Modules                  - Economic Calendar          - Privacy Policy         - LinkedIn
- Pricing                  - Blog                       - Disclaimer             - GitHub
- API Docs                                                                
```

### Dashboard Sidebar (when authenticated)
```
[Logo]

Overview
- Dashboard
- Modules
  - Liquidity
  - Funding
  - Treasury
  - Rates
  - Credit
  - Risk
  - External

Tools
- Economic Calendar
- Encyclopedia
- API Access

Account
- Profile
- Settings
- Billing
- Logout
```

### Breadcrumb Pattern
```
Home > Dashboard
Home > Modules > Liquidity
Home > Encyclopedia > Federal Funds Rate
```

### Mobile Navigation
- Hamburger menu (3-line icon)
- Slide-out drawer from right
- Collapsible sections for Modules
- Full-screen overlay with blur background

---

## 8. Component Library

### Buttons

**Primary Button**
```
Background: var(--accent-primary)
Text: white
Padding: 12px 24px
Border Radius: 10px
Font Weight: 500
Hover: Background darken 10%, translateY(-1px)
Active: Scale 0.98
Transition: all 200ms ease-out-quart
```

**Secondary Button**
```
Background: transparent
Border: 1px solid var(--border)
Text: var(--foreground)
Padding: 12px 24px
Border Radius: 10px
Hover: Background var(--background-secondary)
```

**Ghost Button**
```
Background: transparent
Text: var(--accent-primary)
Padding: 8px 16px
Hover: Background rgba(0, 122, 255, 0.1)
```

### Cards

**Card Academic (Primary)**
```
Background: var(--card)
Border: 1px solid var(--border)
Border Radius: 10px
Padding: 24px
Shadow: var(--shadow-sm)
Hover: translateY(-2px), shadow-lg
Transition: all 250ms ease-out-quart
```

**Card Feature**
```
Background: var(--card)
Border Radius: 16px
Padding: 32px
Icon: 48px, module color
Title: H4
Description: Body small
```

### Inputs

**Text Input**
```
Background: var(--card)
Border: 1px solid var(--border)
Border Radius: 10px
Padding: 12px 16px
Font Size: 16px
Focus: Border var(--accent-primary), shadow 0 0 0 3px rgba(0,122,255,0.1)
Transition: all 200ms ease-out
```

### Score Display

**Score Badge**
```
Size: 48px diameter
Background: Score color (green/yellow/red)
Text: White, bold
Border Radius: 50%
Font Size: 18px
```

**Score Gauge**
```
Size: 280-320px diameter
Arc: 180 degrees (semicircle)
Colors: Red (0-30), Yellow (30-70), Green (70-100)
Needle: Animated rotation
Center Label: Current score
```

### Data Visualization

**Sparkline**
```
Height: 40px
Width: 120px
Stroke: Module color
Stroke Width: 2px
Fill: Gradient fade to transparent
Animation: Draw from left to right
```

**Trend Chart**
```
Height: 300px
Line: 2px stroke, accent color
Fill: Gradient below line
Grid: Subtle horizontal lines
Tooltip: Card style with value and date
```

---

## 9. Responsive Breakpoints

| Breakpoint | Width | Layout Changes |
|------------|-------|----------------|
| Mobile | < 640px | Single column, stacked sections, hamburger nav |
| Tablet | 640-1024px | 2-column grids, condensed spacing |
| Desktop | 1024-1440px | Full layout, 3-4 column grids |
| Wide | > 1440px | Centered content, max-width container |

### Mobile-Specific Adaptations
- Header: Hamburger menu replaces inline nav
- Hero: Reduced padding, smaller gauge (200px)
- Stats: 2x2 grid
- Module cards: Horizontal scroll
- Charts: Simplified, touch-friendly tooltips
- Footer: Single column stack

---

## 10. Accessibility Requirements

### Color Contrast
- Minimum 4.5:1 for normal text
- Minimum 3:1 for large text (18px+)
- Minimum 3:1 for UI components

### Keyboard Navigation
- All interactive elements focusable
- Visible focus indicators
- Logical tab order
- Escape key closes modals/drawers

### Screen Readers
- Semantic HTML structure
- ARIA labels for icons and buttons
- Alt text for images
- Live regions for dynamic content updates

### Motion Preferences
- Respect `prefers-reduced-motion`
- Disable animations for users who prefer reduced motion
- Keep content accessible without animations

---

## 11. Data Integration Notes

### FRED API Integration
- Base URL: https://api.stlouisfed.org/fred/
- Authentication: API key required
- Rate Limit: 120 requests per minute
- Response Format: JSON

### Data Update Schedule
- Daily refresh at 6:00 AM ET
- Real-time indicators updated hourly
- Historical data cached for performance

### Score Calculation
```
Individual Factor Score = Percentile of current value in 5-year history
Module Score = Average of factor scores
Overall Score = Weighted average of module scores
```

### Caching Strategy
- API responses cached for 1 hour
- Historical data cached for 24 hours
- Static assets cached with version hashes

---

*Document Version: 1.0*
*Last Updated: 2024*
*Platform: The Dial - Macroeconomic Research Dashboard*
