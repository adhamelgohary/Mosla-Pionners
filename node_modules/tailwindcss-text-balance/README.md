# tailwindcss-text-balance

[![npm](https://img.shields.io/npm/v/tailwindcss-text-balance?style=shield)
](https://www.npmjs.com/package/tailwindcss-text-balance)

Adds utilty classes for `text-wrap: balance` and `text-wrap: pretty` in Tailwind CSS.

This plugin is intended to act as a stepping stone until tailwindcss supports `text-wrap: balance` natively.
It aims to act as a drop-in
for [tailwindcss pull request #11320](https://github.com/tailwindlabs/tailwindcss/pull/11320).

See the [Chrome Developers Blog](https://developer.chrome.com/blog/css-text-wrap-balance/) for more
information about `text-wrap: balance` in CSS and why it's useful.

## Installation

```sh
npm install tailwindcss-text-balance
```

## Usage

```js
// tailwind.config.js
module.exports = {
  plugins: [
    require('tailwindcss-text-balance'),
  ],
}
```

This plugin generates the following utilities when the classes are used:

```css
.text-balance {
    text-wrap: balance;
}

.text-pretty {
    text-wrap: pretty;
}

.text-wrap {
    text-wrap: wrap;
}

.text-nowrap {
    text-wrap: nowrap;
}
```

Not all browsers support `text-wrap: balance` yet. You can use the
[CSS.supports()](https://developer.mozilla.org/en-US/docs/Web/API/CSS/supports) method to check if
the browser supports it before using it.

This plugin does not include a polyfill for `text-wrap: balance`.

## License

This project is licensed under the [MIT License](LICENSE.md).

## Contributing

Pull requests are welcome! For major changes, please open an issue first to discuss what you would like to change.