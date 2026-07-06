// Simplified brand marks for connected source systems.
// Drawn inline so no external assets are needed.

type P = { size?: number; className?: string };

export function JiraIcon({ size = 20, className }: P) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden>
      <path d="M12 2 4.6 9.4a1.4 1.4 0 0 0 0 2L12 18.8l2.9-2.9-4.5-4.5L14.9 6.9 12 2z" fill="#2684FF" />
      <path d="M12 5.2 19.4 12.6a1.4 1.4 0 0 1 0 2L12 22l-2.9-2.9 4.5-4.5-4.5-4.5L12 5.2z" fill="#2684FF" opacity=".55" />
    </svg>
  );
}

export function ConfluenceIcon({ size = 20, className }: P) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden>
      <path d="M3 17.5c2.6-4.3 5-5.4 8.2-3.8l6.3 3-2 4.2-6-2.9c-1.5-.7-2.4-.4-3.8 1.8L3 17.5z" fill="#2684FF" />
      <path d="M21 6.5c-2.6 4.3-5 5.4-8.2 3.8l-6.3-3 2-4.2 6 2.9c1.5.7 2.4.4 3.8-1.8L21 6.5z" fill="#5B5CEB" />
    </svg>
  );
}

export function SlackIcon({ size = 20, className }: P) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden>
      <path d="M9.5 2.5a2 2 0 1 0 0 4h2v-2a2 2 0 0 0-2-2zM9.5 8H4.5a2 2 0 1 0 0 4h5a2 2 0 1 0 0-4z" fill="#36C5F0" />
      <path d="M21.5 9.5a2 2 0 1 0-4 0v2h2a2 2 0 0 0 2-2zM16 9.5v-5a2 2 0 1 0-4 0v5a2 2 0 1 0 4 0z" fill="#2EB67D" />
      <path d="M14.5 21.5a2 2 0 1 0 0-4h-2v2a2 2 0 0 0 2 2zM14.5 16h5a2 2 0 1 0 0-4h-5a2 2 0 1 0 0 4z" fill="#ECB22E" />
      <path d="M2.5 14.5a2 2 0 1 0 4 0v-2h-2a2 2 0 0 0-2 2zM8 14.5v5a2 2 0 1 0 4 0v-5a2 2 0 1 0-4 0z" fill="#E01E5A" />
    </svg>
  );
}

export function TeamsIcon({ size = 20, className }: P) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden>
      <circle cx="17" cy="8" r="3" fill="#7B83EB" opacity=".7" />
      <rect x="2" y="6" width="12" height="12" rx="2.5" fill="#5059C9" />
      <path d="M5 9.5h6M8 9.5V15" stroke="#fff" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M15 12h5v4.5a4 4 0 0 1-5 3.9V12z" fill="#7B83EB" />
    </svg>
  );
}

export function GitHubIcon({ size = 20, className }: P) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden>
      <path
        fill="#171a2c"
        d="M12 2C6.48 2 2 6.58 2 12.25c0 4.53 2.87 8.37 6.84 9.72.5.1.68-.22.68-.49v-1.7c-2.78.62-3.37-1.37-3.37-1.37-.45-1.18-1.11-1.5-1.11-1.5-.9-.64.07-.62.07-.62 1 .07 1.53 1.05 1.53 1.05.89 1.56 2.34 1.11 2.91.85.09-.66.35-1.11.63-1.37-2.22-.26-4.56-1.14-4.56-5.07 0-1.12.39-2.03 1.03-2.75-.1-.26-.45-1.3.1-2.7 0 0 .84-.28 2.75 1.05a9.36 9.36 0 0 1 5 0c1.91-1.33 2.75-1.05 2.75-1.05.55 1.4.2 2.44.1 2.7.64.72 1.03 1.63 1.03 2.75 0 3.94-2.34 4.8-4.57 5.06.36.32.68.94.68 1.9v2.82c0 .27.18.6.69.49A10.05 10.05 0 0 0 22 12.25C22 6.58 17.52 2 12 2z"
      />
    </svg>
  );
}

export function GitLabIcon({ size = 20, className }: P) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden>
      <path d="m12 21 3.7-11.4h-7.4L12 21z" fill="#E24329" />
      <path d="m12 21-3.7-11.4H3.1L12 21z" fill="#FC6D26" />
      <path d="M3.1 9.6 2 13.1a.77.77 0 0 0 .28.86L12 21 3.1 9.6z" fill="#FCA326" />
      <path d="M3.1 9.6h5.2L6.06 2.72a.38.38 0 0 0-.73 0L3.1 9.6z" fill="#E24329" />
      <path d="m12 21 3.7-11.4h5.2L12 21z" fill="#FC6D26" />
      <path d="m20.9 9.6 1.1 3.5a.77.77 0 0 1-.28.86L12 21l8.9-11.4z" fill="#FCA326" />
      <path d="M20.9 9.6h-5.2l2.24-6.88a.38.38 0 0 1 .73 0L20.9 9.6z" fill="#E24329" />
    </svg>
  );
}

export function SharePointIcon({ size = 20, className }: P) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden>
      <circle cx="10" cy="8" r="6" fill="#036C70" />
      <circle cx="16.5" cy="12.5" r="5" fill="#1A9BA1" />
      <circle cx="11" cy="17" r="4.5" fill="#37C6D0" />
      <rect x="4" y="8.5" width="9" height="9" rx="1.6" fill="#03787C" />
      <path d="M6.8 14.7c.5.4 1.2.6 1.9.6 1.4 0 2.3-.7 2.3-1.8 0-.9-.5-1.4-1.8-1.7-.9-.2-1.2-.4-1.2-.8s.4-.7 1-.7c.6 0 1.2.2 1.7.5v-1.2a3.8 3.8 0 0 0-1.7-.4c-1.3 0-2.2.7-2.2 1.8 0 .9.6 1.4 1.8 1.7.9.2 1.2.4 1.2.8 0 .5-.4.7-1.1.7-.7 0-1.4-.3-1.9-.7v1.2z" fill="#fff" />
    </svg>
  );
}

export function GoogleDriveIcon({ size = 20, className }: P) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden>
      <path d="M8.6 3h6.8l6.3 11h-6.8L8.6 3z" fill="#FFCF63" />
      <path d="M8.6 3 2.3 14l3.4 6L12 9 8.6 3z" fill="#11A861" />
      <path d="M5.7 20h12.9l3.1-6H9.1l-3.4 6z" fill="#4688F4" />
    </svg>
  );
}

export function NotionIcon({ size = 20, className }: P) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden>
      <rect x="3" y="3" width="18" height="18" rx="3.5" fill="#fff" stroke="#171a2c" strokeWidth="1.5" />
      <path d="M8 17V7.5l1.8-.1L15 14V7h1.5v9.5l-1.9.1L9.5 9.8V17H8z" fill="#171a2c" />
    </svg>
  );
}

export function PdfIcon({ size = 20, className }: P) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden>
      <path d="M6 2h8l4 4v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" fill="#F04438" opacity=".14" />
      <path d="M6 2h8l4 4v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" stroke="#F04438" strokeWidth="1.5" fill="none" />
      <text x="12" y="16" textAnchor="middle" fontSize="6.4" fontWeight="700" fill="#F04438">PDF</text>
    </svg>
  );
}

export function CVUMMark({ size = 26, className }: P) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" className={className} aria-hidden>
      <defs>
        <linearGradient id="km-g" x1="0" y1="0" x2="32" y2="32">
          <stop offset="0%" stopColor="#8583f1" />
          <stop offset="100%" stopColor="#5b5ceb" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill="url(#km-g)" />
      <path d="M10 8v16M10 16l9-8M10 16l9 8" stroke="#fff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
