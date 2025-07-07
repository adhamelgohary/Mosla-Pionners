// tailwind.config.js
const colors = require('tailwindcss/colors');
const plugin = require('tailwindcss/plugin');

/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ['selector', '[data-theme="dark"]'],
  
  content: [
    './routes/**/*.html',
    './templates/**/*.html',
    './utils/**/*.html',
    './**/templates/**/*.html'
  ],
  
  theme: {
    extend: {
      // --- 1. ENHANCED THEME & DESIGN SYSTEM ---
      colors: {
        primary: {
          DEFAULT: 'rgb(var(--primary-color-rgb) / <alpha-value>)',
          darker: 'var(--primary-color-darker)',
        },
        secondary: {
          DEFAULT: 'rgb(var(--secondary-color-rgb) / <alpha-value>)',
        },
        background: 'var(--background-color)',
        card: 'var(--card-bg)',
        input: 'var(--input-bg-color)',
        text: {
          DEFAULT: 'var(--text-color)',
          main: 'var(--text-color)',
          muted: 'var(--text-muted)',
        },
        heading: 'var(--heading-color)',
        border: 'var(--border-color)',
        'input-border': 'var(--input-border-color)',
        
        // Semantic alert colors
        alert: {
          success: { bg: colors.green[50], text: colors.green[700], border: colors.green[200] },
          danger: { bg: colors.red[50], text: colors.red[700], border: colors.red[200] },
        },
        
        tag: {
            location: { bg: 'var(--tag-location-bg)', text: 'var(--tag-location-text)' },
            category: { bg: 'var(--tag-category-bg)', text: 'var(--tag-category-text)' },
            english: { bg: 'var(--tag-english-bg)', text: 'var(--tag-english-text)' }
        },
        // Base utility colors remain
        success: colors.green,
        danger: { DEFAULT: 'var(--danger-color)', ...colors.red },
        warning: colors.amber,
      },
      
      // Consistent spacing scale (0.25rem = 4px)
      spacing: {
        '128': '32rem', // Example of adding a large size
      },

      // Consistent border radius scale
      borderRadius: {
        'sm': '0.125rem', // 2px
        'DEFAULT': '0.25rem', // 4px
        'md': '0.375rem', // 6px
        'lg': '0.5rem', // 8px
        'xl': '0.75rem', // 12px
        '2xl': '1rem', // 16px
        '3xl': '1.5rem', // 24px
        'full': '9999px',
      },

      fontFamily: {
        sans: ['Poppins', 'Arial', 'sans-serif'],
      },
      
      boxShadow: {
        DEFAULT: 'var(--card-shadow)',
      },
      
      // --- 2. POWERFUL ANIMATIONS ---
      keyframes: {
        // For general use fade-in animations
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'fade-in-up': {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        // For tailwindcss-animate plugin
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
      },
      animation: {
        'fade-in': 'fade-in 0.5s ease-out forwards',
        'fade-in-up': 'fade-in-up 0.5s ease-out forwards',
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
      },

      typography: ({ theme }) => ({
        DEFAULT: {
          css: {
            '--tw-prose-body': theme('colors.text.muted'),
            '--tw-prose-headings': theme('colors.heading'),
            '--tw-prose-links': theme('colors.primary.DEFAULT'),
            '--tw-prose-bold': theme('colors.text.main'),
            '--tw-prose-invert-body': theme('colors.text.muted'),
            '--tw-prose-invert-headings': theme('colors.heading'),
            '--tw-prose-invert-links': theme('colors.primary.DEFAULT'),
            '--tw-prose-invert-bold': theme('colors.text.main'),
          },
        },
      }),
    },
  },
  
  plugins: [
    // Official plugins
    require('@tailwindcss/forms'),
    require('@tailwindcss/typography'),
    require('@tailwindcss/aspect-ratio'),
    
    // --- 3. ADVANCED PLUGINS ---
    require('@tailwindcss/container-queries'), // For container-based responsive design
    require('tailwindcss-text-balance'),    // For prettier text wrapping in headlines
    
    // UI and animation plugins
    require('tailwindcss-animate'),
    require('@headlessui/tailwindcss')({ prefix: 'ui' }),

    // --- 4. DX ENHANCEMENTS ---
    // Custom variant for applying styles on both hover and focus
    plugin(function({ addVariant }) {
      addVariant('hocus', ['&:hover', '&:focus'])
    }),
  ],
};