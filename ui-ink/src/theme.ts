export type Theme = { accent: string; muted: string; line: string; danger: string; success: string; warning: string };
export const themes: Record<'graphite' | 'light', Theme> = {
  graphite: {
    accent: '#80B9CE',
    muted: '#A4AAB3',
    line: '#545C68',
    danger: '#F29398',
    success: '#A8C9B0',
    warning: '#DDC489',
  },
  light: {
    accent: '#18576F',
    muted: '#505C68',
    line: '#84939D',
    danger: '#9F2D3A',
    success: '#346743',
    warning: '#785C12',
  },
};
