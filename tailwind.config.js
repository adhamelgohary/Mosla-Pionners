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
    fluidType: {
      settings: {
        fontSizeMin: 1.125,
        fontSizeMax: 1.25,
        ratioMin: 1.125,     
        ratioMax: 1.2,      
        screenMin: 20,       
        screenMax: 96,       
        unit: 'rem',
        prefix: 'fluid-',
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
    require('@tailwindcss/forms'),
    require('@tailwindcss/typography'),
    require('@tailwindcss/aspect-ratio'),
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

    plugin(function({ addBase, addComponents, addVariant }) {
      addBase({
        ':root': {
          '--primary-color-rgb': '59 130 246', '--primary-color-darker': '#1d4ed8', '--secondary-color-rgb': '16 185 129',
          '--danger-color': '#ef4444', '--background-color': '#f9fafb', '--card-bg': '#ffffff', '--input-bg-color': '#ffffff',
          '--text-color': '#374151', '--text-muted': '#6b7280', '--heading-color': '#111827',
          '--border-color': '#e5e7eb', '--input-border-color': '#d1d5db',
          '--card-shadow': '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)',
        },
        '[data-theme="dark"]': {
          '--primary-color-rgb': '96 165 250', '--primary-color-darker': '#60a5fa', '--secondary-color-rgb': '52 211 153',
          '--danger-color': '#f87171', '--background-color': '#111827', '--card-bg': '#1f2937', '--input-bg-color': '#374151',
          '--text-color': '#d1d5db', '--text-muted': '#9ca3af', '--heading-color': '#f9fafb',
          '--border-color': '#374151', '--input-border-color': '#4b5563',
          '--card-shadow': '0 4px 6px -1px rgb(0 0 0 / 0.2), 0 2px 4px -2px rgb(0 0 0 / 0.2)',
        }
      });

      // --- [THE FIX] ---
      // This section is now empty. By not defining global .form-input or .btn-primary styles here,
      // we prevent conflicts with pages like the Bento grid that use specific, local utility classes for styling.
      // Other pages can now use the default styles from the @tailwindcss/forms plugin without issue.
      addComponents({
        // Intentionally left blank to avoid global style overrides.
      });

      addVariant('hocus', ['&:hover', '&:focus']);
    }),
  ],
};