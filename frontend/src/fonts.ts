// Self-hosted Noto faces (SIL OFL 1.1), bundled with the app instead of loaded from Google Fonts:
// no visitor IP is sent to a third party on page load (privacy model), and the CSP can stay
// 'self'-only for styles and fonts. Each weight file declares unicode-range subsets, so browsers
// download only the scripts a page actually renders (Latin, Devanagari, Tamil…).
import "@fontsource/noto-sans/400.css";
import "@fontsource/noto-sans/500.css";
import "@fontsource/noto-sans/600.css";
import "@fontsource/noto-sans/700.css";
import "@fontsource/noto-sans-devanagari/400.css";
import "@fontsource/noto-sans-devanagari/500.css";
import "@fontsource/noto-sans-devanagari/600.css";
import "@fontsource/noto-sans-devanagari/700.css";
import "@fontsource/noto-sans-tamil/400.css";
import "@fontsource/noto-sans-tamil/600.css";
import "@fontsource/noto-serif/600.css";
import "@fontsource/noto-serif/700.css";
import "@fontsource/noto-serif-devanagari/600.css";
import "@fontsource/noto-serif-devanagari/700.css";
