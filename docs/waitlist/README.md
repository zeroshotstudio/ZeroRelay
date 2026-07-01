# Waitlist page setup

Static page: `docs/waitlist/index.html`

## Host options

1. **GitHub Pages** — enable Pages from `/docs` on `main`; live at  
   `https://zeroshotstudio.github.io/ZeroRelay/waitlist/`

2. **relay.zeroshot.studio** — Caddy/nginx static file or reverse proxy to Pages

## Form backend

1. Create a free form at [formspree.io](https://formspree.io) → copy form ID
2. Replace `action` in `index.html`:
   ```html
   action="https://formspree.io/f/YOUR_FORM_ID"
   ```

Submissions email `git@zeroshot.studio` (or your Formspree inbox).

## Fields collected

- Email
- Agent count (1–2 / 3–5 / 6+)
- Hosting preference (self-host / Cloud Solo / Managed Stack)
