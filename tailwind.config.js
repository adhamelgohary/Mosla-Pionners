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
    // === CHANGE 1: Toning down the fluid typography scale ===
    fluidType: {
      settings: {
        fontSizeMin: 1.0,    // Base size remains 16px on mobile
        fontSizeMax: 1.125,  // Max size is now 18px instead of 20px
        ratioMin: 1.1,       
        ratioMax: 1.15,      // Headings will be less dramatically larger
        screenMin: 20,       
        screenMax: 96,       
        unit: 'rem',
        prefix: 'fluid-',
      },
    },
    extend: {
      // (The rest of your theme.extend section remains the same)
      colors: {
        primary: {
          DEFAULT: 'rgb(var(--primary-color-rgb) / <alpha-value>)',
          darker: 'var(--primary-color-darker)',
        },
        secondary: { DEFAULT: 'rgb(var(--secondary-color-rgb) / <alpha-value>)', },
        background: 'var(--background-color)',
        card: 'var(--card-bg)',
        input: 'var(--input-bg-color)',
        text: {
          DEFAULT: 'var(--text-color)', main: 'var(--text-color)', muted: 'var(--text-muted)',
        },
        heading: 'var(--heading-color)',
        border: 'var(--border-color)',
        'input-border': 'var(--input-border-color)',
        alert: {
          success: { bg: colors.green[50], text: colors.green[700], border: colors.green[200] },
          danger: { bg: colors.red[50], text: colors.red[700], border: colors.red[200] },
        },
        tag: {
            location: { bg: 'var(--tag-location-bg)', text: 'var(--tag-location-text)' },
            category: { bg: 'var(--tag-category-bg)', text: 'var(--tag-category-text)' },
            english: { bg: 'var(--tag-english-bg)', text: 'var(--tag-english-text)' }
        },
        success: colors.green,
        danger: { DEFAULT: 'var(--danger-color)', ...colors.red },
        warning: colors.amber,
      },
      borderRadius: {
        'sm': '0.125rem', 'DEFAULT': '0.25rem', 'md': '0.375rem', 'lg': '0.5rem',
        'xl': '0.75rem', '2xl': '1rem', '3xl': '1.5rem', 'full': '9999px',
      },
      fontFamily: {
        sans: ['Poppins', 'Arial', 'sans-serif'],
      },
      boxShadow: {
        DEFAULT: 'var(--card-shadow)',
        lg: '0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)',
      },
      keyframes: {
        'fade-in': { '0%': { opacity: '0' }, '100%': { opacity: '1' }, },
        'fade-in-up': { '0%': { opacity: '0', transform: 'translateY(10px)' }, '100%': { opacity: '1', transform: 'translateY(0)' }, },
        "accordion-down": { from: { height: "0" }, to: { height: "var(--radix-accordion-content-height)" }, },
        "accordion-up": { from: { height: "var(--radix-accordion-content-height)" }, to: { height: "0" }, },
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
            '--tw-prose-body': theme('colors.text.muted'), '--tw-prose-headings': theme('colors.heading'),
            '--tw-prose-links': theme('colors.primary.DEFAULT'), '--tw-prose-bold': theme('colors.text.main'),
            '--tw-prose-invert-body': theme('colors.text.muted'), '--tw-prose-invert-headings': theme('colors.heading'),
            '--tw-prose-invert-links': theme('colors.primary.DEFAULT'), '--tw-prose-invert-bold': theme('colors.text.main'),
          },
        },
      }),
    },
  },
  
  plugins: [
    // --- OFFICIAL PLUGINS ---
    require('@tailwindcss/forms'),
    require('@tailwindcss/typography'),
    require('@tailwindcss/aspect-ratio'),
    
    // --- 3RD PARTY PLUGINS ---
    require('@tailwindcss/container-queries'),
    require('tailwindcss-text-balance'),
    require('tailwindcss-fluid-type'),
    require('tailwindcss-gradients'),
    require('tailwindcss-children'),
    require('@mertasan/tailwindcss-variables'),
    require('tailwindcss-pseudo-elements'),
    require('tailwindcss-scrollbar'),
    require('tailwindcss-animate'),
    require('@headlessui/tailwindcss')({ prefix: 'ui' }),

    // --- CUSTOM IN-LINE PLUGIN (WITH NEW COMPACT STYLES) ---
    plugin(function({ addBase, addComponents, addVariant }) {
      // 1. ADD BASE STYLES AND CSS VARIABLES
      addBase({
        // DEFAULT THEME (for public site)
        ':root': {
          'font-size': '14px', 
          '--primary-color-rgb': '59 130 246', // Blue
          '--primary-color-darker': '#1d4ed8', 
          '--secondary-color-rgb': '16 185 129', // Emerald
          '--danger-color': '#ef4444', 
          '--background-color': '#f9fafb', // Gray 50
          '--card-bg': '#ffffff', 
          '--input-bg-color': '#ffffff',
          '--text-color': '#374151', // Gray 700
          '--text-muted': '#6b7280', // Gray 500
          '--heading-color': '#111827', // Gray 900
          '--border-color': '#e5e7eb', // Gray 200
          '--input-border-color': '#d1d5db', // Gray 300
          '--card-shadow': '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)',
        },
        // DEFAULT DARK THEME (for public site)
        '[data-theme="dark"]': {
          '--primary-color-rgb': '96 165 250', '--primary-color-darker': '#60a5fa', 
          '--secondary-color-rgb': '52 211 153', '--danger-color': '#f87171', 
          '--background-color': '#111827', '--card-bg': '#1f2937', 
          '--input-bg-color': '#374151', '--text-color': '#d1d5db', 
          '--text-muted': '#9ca3af', '--heading-color': '#f9fafb',
          '--border-color': '#374151', '--input-border-color': '#4b5563',
          '--card-shadow': '0 4px 6px -1px rgb(0 0 0 / 0.2), 0 2px 4px -2px rgb(0 0 0 / 0.2)',
        },

        // ##### NEW PORTAL THEME (LIGHT) #####
        // When .portal-scope is present, these variables will override the :root defaults.
        '.portal-scope': {
            '--primary-color-rgb': '79 70 229',  // Indigo 600
            '--primary-color-darker': '#4338ca', // Indigo 700
            '--secondary-color-rgb': '219 39 119', // Pink 600
            '--background-color': '#f1f5f9',    // Slate 100
            '--card-bg': '#ffffff',
            '--text-color': '#334155',         // Slate 700
            '--text-muted': '#64748b',         // Slate 500
            '--heading-color': '#0f172a',      // Slate 900
            '--border-color': '#e2e8f0',       // Slate 200
            '--input-border-color': '#cbd5e1', // Slate 300
        },
        // ##### NEW PORTAL THEME (DARK) #####
        // When both data-theme="dark" and .portal-scope are present, this is used.
        '[data-theme="dark"].portal-scope': {
            '--primary-color-rgb': '129 140 248', // Indigo 400
            '--primary-color-darker': '#a5b4fc',  // Indigo 300
            '--background-color': '#0f172a',    // Slate 900
            '--card-bg': '#1e293b',             // Slate 800
            '--text-color': '#cbd5e1',         // Slate 300
            '--text-muted': '#94a3b8',         // Slate 400
            '--heading-color': '#f1f5f9',      // Slate 100
            '--border-color': '#334155',       // Slate 700
            '--input-border-color': '#475569', // Slate 600
        }
      });

      // 2. ADD CUSTOM COMPONENT CLASSES (MORE COMPACT)
      addComponents({
        '.form-label': {
          '@apply block text-xs font-medium leading-6 text-text': {}, // smaller label text
        },
        '.form-input, .form-select, .form-textarea': {
          // py-1 for less height
          '@apply mt-1 block w-full rounded-md border-input-border bg-input shadow-sm px-2 py-1 text-sm hocus:border-primary hocus:ring hocus:ring-primary/20 transition-all duration-300': {},
        },
        '.form-checkbox, .form-radio': {
          '@apply rounded border-input-border text-primary focus:ring-primary': {},
        },
        '.btn-primary, .btn-secondary': {
            // py-1.5 for shorter buttons, text-xs for smaller text
            '@apply inline-flex items-center justify-center rounded-md px-3 py-1.5 text-xs font-semibold shadow-sm transition-all duration-300': {},
        },
        '.btn-primary': {
            '@apply bg-primary text-white hocus:bg-primary-darker hocus:scale-105': {},
        },
        '.btn-secondary': {
            '@apply bg-card text-text ring-1 ring-inset ring-border hocus:bg-background hocus:ring-primary': {},
        },
      });

      addVariant('hocus', ['&:hover', '&:focus']);
    }),
  ],
};