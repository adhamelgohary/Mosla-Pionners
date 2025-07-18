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
    // NOTE: All your theme extensions from before remain the same.
    // This part is unchanged.
    fluidType: {
      settings: {
        fontSizeMin: 1.0, fontSizeMax: 1.25, ratioMin: 1.1, ratioMax: 1.2,
        screenMin: 20, screenMax: 96, unit: 'rem', prefix: 'fluid-',
      },
    },
    extend: {
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
        lg: '0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)', // Example of keeping default shadows
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

    // --- CUSTOM IN-LINE PLUGIN FOR BASE STYLES AND VARIABLES ---
    plugin(function({ addBase, addComponents, addVariant }) {
      // 1. ADD BASE STYLES AND CSS VARIABLES
      addBase({
        ':root': {
          '--primary-color-rgb': '59 130 246', // blue-500
          '--primary-color-darker': '#1d4ed8', // blue-700
          '--secondary-color-rgb': '16 185 129', // emerald-500
          '--danger-color': '#ef4444', // red-500
          '--background-color': '#f9fafb', // gray-50
          '--card-bg': '#ffffff',
          '--input-bg-color': '#ffffff',
          '--text-color': '#374151', // gray-700
          '--text-muted': '#6b7280', // gray-500
          '--heading-color': '#111827', // gray-900
          '--border-color': '#e5e7eb', // gray-200
          '--input-border-color': '#d1d5db', // gray-300
          '--card-shadow': '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)',
        },
        '[data-theme="dark"]': {
          '--primary-color-rgb': '96 165 250', // blue-400
          '--primary-color-darker': '#60a5fa', // blue-400
          '--secondary-color-rgb': '52 211 153', // emerald-400
          '--danger-color': '#f87171', // red-400
          '--background-color': '#111827', // gray-900
          '--card-bg': '#1f2937', // gray-800
          '--input-bg-color': '#374151', // gray-700
          '--text-color': '#d1d5db', // gray-300
          '--text-muted': '#9ca3af', // gray-400
          '--heading-color': '#f9fafb', // gray-50
          '--border-color': '#374151', // gray-700
          '--input-border-color': '#4b5563', // gray-600
          '--card-shadow': '0 4px 6px -1px rgb(0 0 0 / 0.2), 0 2px 4px -2px rgb(0 0 0 / 0.2)',
        }
      });

      // 2. ADD CUSTOM COMPONENT CLASSES
      addComponents({
        '.form-label': {
          '@apply block text-sm font-medium leading-6 text-text': {},
        },
        '.form-input, .form-select, .form-textarea': {
          '@apply mt-1 block w-full rounded-md border-input-border bg-input shadow-sm hocus:border-primary hocus:ring hocus:ring-primary/20 transition-all duration-300': {},
        },
        '.form-checkbox, .form-radio': {
          '@apply rounded border-input-border text-primary focus:ring-primary': {},
        },
        '.btn-primary': {
            '@apply inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-semibold text-white shadow-sm transition-all duration-300 hocus:bg-primary-darker hocus:scale-105': {},
        },
        '.btn-secondary': {
            '@apply inline-flex items-center justify-center rounded-md bg-card px-4 py-2 text-sm font-semibold text-text shadow-sm ring-1 ring-inset ring-border transition-all duration-300 hocus:bg-background hocus:ring-primary': {},
        },
      });

      // 3. ADD CUSTOM VARIANTS
      addVariant('hocus', ['&:hover', '&:focus']);
    }),
  ],
};