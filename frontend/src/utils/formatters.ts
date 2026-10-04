export const formatCurrency = (value: number | string): string => {
  const num = typeof value === 'string' ? parseFloat(value) : value;
  if (isNaN(num)) return '$0';
  
  if (num >= 1e9) {
    return `$${(num / 1e9).toFixed(2)}B`;
  }
  if (num >= 1e6) {
    return `$${(num / 1e6).toFixed(2)}M`;
  }
  if (num >= 1e3) {
    return `$${(num / 1e3).toFixed(1)}K`;
  }
  return `$${num.toFixed(0)}`;
};

export const formatPercent = (value: number | string): string => {
  const num = typeof value === 'string' ? parseFloat(value) : value;
  if (isNaN(num)) return '0%';
  return `${(num * 100).toFixed(1)}%`;
};
