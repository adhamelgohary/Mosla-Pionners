// tailwind.config.js
const colors = require('tailwindcss/colors');

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
      colors: {
        // --- BASE THEME COLORS (from your CSS variables) ---
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
        
        // --- NEW: TAG COLORS MIGRATED FROM CSS ---
        // This allows you to use classes like `bg-tag-location-bg`
        tag: {
            location: { 
                bg: 'var(--tag-location-bg)', 
                text: 'var(--tag-location-text)' 
            },
            category: { 
                bg: 'var(--tag-category-bg)', 
                text: 'var(--tag-category-text)' 
            },
            english: { 
                bg: 'var(--tag-english-bg)', 
                text: 'var(--tag-english-text)' 
            }
        },

        // --- UTILITY COLORS ---
        success: colors.green,
        danger: { DEFAULT: 'var(--danger-color)', ...colors.red },
        warning: colors.amber,
        info: colors.sky,
        gray: colors.gray,
      },
      
      fontFamily: {
        sans: ['Poppins', 'Arial', 'sans-serif'],
      },
      
      boxShadow: {
        DEFAULT: 'var(--card-shadow)',
      },
      
      typography: ({ theme }) => ({
        DEFAULT: {
          css: {
            '--tw-prose-body': theme('colors.text.muted'),
            '--tw-prose-headings': theme('colors.heading'),
            '--tw-prose-lead': theme('colors.text.main'),
            '--tw-prose-links': theme('colors.primary.DEFAULT'),
            '--tw-prose-bold': theme('colors.text.main'),
            '--tw-prose-counters': theme('colors.text.muted'),
            '--tw-prose-bullets': theme('colors.border'),
            '--tw-prose-hr': theme('colors.border'),
            '--tw-prose-quotes': theme('colors.text.main'),
            '--tw-prose-quote-borders': theme('colors.border'),
            '--tw-prose-captions': theme('colors.text.muted'),
            '--tw-prose-code': theme('colors.text.main'),
            '--tw-prose-pre-code': theme('colors.text.muted'),
            '--tw-prose-pre-bg': theme('colors.input'),
            '--tw-prose-th-borders': theme('colors.border'),
            '--tw-prose-td-borders': theme('colors.border'),
            // Add dark mode support for prose
            '--tw-prose-invert-body': theme('colors.text.muted'),
            '--tw-prose-invert-headings': theme('colors.heading'),
            '--tw-prose-invert-lead': theme('colors.text.main'),
            '--tw-prose-invert-links': theme('colors.primary.DEFAULT'),
            '--tw-prose-invert-bold': theme('colors.text.main'),
          },
        },
      }),
    },
  },
  
  plugins: [
    require('@tailwindcss/forms'),
    require('@tailwindcss/typography'),
    require('@tailwindcss/aspect-ratio'),
    require('tailwindcss-animate'),
    require('@headlessui/tailwindcss')({ prefix: 'ui' }),
  ],
};