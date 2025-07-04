// tailwind.config.js
const colors = require('tailwindcss/colors');

/** @type {import('tailwindcss').Config} */
module.exports = {
  // This darkMode strategy looks for the `data-theme="dark"` attribute on the <html> tag
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
        // --- THEME-AWARE COLORS ---
        // These colors will automatically switch between light and dark
        // based on the CSS variables defined in your main website CSS file.
        // We use RGB variables here because your CSS file provides them, which is great for opacity.
        primary: {
          DEFAULT: 'rgb(var(--primary-color-rgb) / <alpha-value>)',
          darker: 'var(--primary-color-darker)',
        },
        secondary: {
          DEFAULT: 'rgb(var(--secondary-color-rgb) / <alpha-value>)',
        },
        
        // Background and surface colors
        background: 'var(--background-color)',
        card: 'var(--card-bg)',
        input: 'var(--input-bg-color)',
        
        // Text colors (we create a nested 'text' object for organization)
        text: {
          DEFAULT: 'var(--text-color)', // Allows using `text-text` instead of `text-text-main`
          main: 'var(--text-color)',
          muted: 'var(--text-muted)',
        },
        heading: 'var(--heading-color)',
        
        // Border colors
        border: 'var(--border-color)',
        'input-border': 'var(--input-border-color)',
        
        // Job Tag colors (nested for organization)
        tag: {
            location: {
                bg: 'var(--tag-location-bg)',
                text: 'var(--tag-location-text)',
            },
            category: {
                bg: 'var(--tag-category-bg)',
                text: 'var(--tag-category-text)',
            },
            english: {
                bg: 'var(--tag-english-bg)',
                text: 'var(--tag-english-text)',
            }
        },
        
        // --- STATIC COLORS ---
        // Standard colors for alerts, etc. that don't need to change with the theme.
        // We keep these separate for clarity.
        success: colors.green,
        danger: {
            DEFAULT: 'var(--danger-color)', // Use your CSS variable for consistency
            ...colors.red // Keep other shades like 'danger-500' if needed
        },
        warning: colors.amber,
        info: colors.sky,
        gray: colors.gray, // Include neutral grays for general use
      },
      
      fontFamily: {
        // Your font family from --font-family
        sans: ['Poppins', 'Arial', 'sans-serif'],
      },
      
      boxShadow: {
        // Replicating your custom card shadow
        DEFAULT: 'var(--card-shadow)',
      },

      gradientColorStops: {
        // Replicating your custom gradients
        'highlight-start': 'var(--secondary-color)',
        'highlight-end': '#4a9eff', // This was a static color in your gradient
        'dark-section-start': '#2c5aa0',
        'dark-section-end': '#1e3f73',
      },

      backgroundImage: {
        // Making your header gradients available as utilities like `bg-header-gradient`
        'header-gradient': 'var(--header-bg)',
        'dark-section-gradient': 'var(--dark-section-bg)',
      },
    },
  },
  
  plugins: [
    // These plugins are now installed and ready to be used.
    require('@tailwindcss/forms'),
    require('@tailwindcss/typography'),
    require('@tailwindcss/aspect-ratio'),
    require('tailwindcss-animate'),
    require('@headlessui/tailwindcss')({ prefix: 'ui' }), // prefix is optional but recommended
  ],
};