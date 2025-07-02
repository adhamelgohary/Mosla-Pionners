// tailwind.config.js
const colors = require('tailwindcss/colors');

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
      // Here we translate your CSS variables into Tailwind's theme object
      colors: {
        // Your color palette from :root
        primary: {
          DEFAULT: '#2c5aa0', // from --primary-color
          darker: '#214070', // from --primary-color-darker
        },
        secondary: '#62bfe6', // from --secondary-color
        
        // Background and surface colors
        'background': '#ffffff', // from --background-color
        'card': '#ffffff',      // from --card-bg
        'input': '#ffffff',     // from --input-bg-color
        
        // Text colors
        'text-main': '#403e3e',   // from --text-color
        'text-muted': '#666666',   // from --text-muted
        'heading': '#1a2a4d',     // from --heading-color

        // Dark mode equivalents from html[data-theme="dark"]
        dark: {
          primary: '#6fc6d8',
          secondary: '#87CEEB',
          background: '#111827',
          card: '#1e2945',
          input: '#2d3748',
          text: {
            main: '#e0e0e0',
            muted: '#a0a0a0',
          },
          heading: '#F9FAFB',
          border: '#374151',
        },
        
        // Standard colors for alerts etc.
        success: colors.green,
        danger: colors.red,
        warning: colors.amber,
        info: colors.sky,
      },
      fontFamily: {
        // Your font family from --font-family
        sans: ['Poppins', 'Arial', 'sans-serif'],
      },
    },
  },
  
  plugins: [
    require('@tailwindcss/forms'),
    require('@tailwindcss/typography'),
  ],
};