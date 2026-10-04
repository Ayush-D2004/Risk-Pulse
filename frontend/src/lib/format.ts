export const formatCurrency = (value: string | number | undefined): string => {
  if (value === undefined || value === null) return '$0.00';
  const num = typeof value === 'string' ? parseFloat(value) : value;
  if (isNaN(num)) return '$0.00';
  
  const absNum = Math.abs(num);
  let formatted = '';
  
  if (absNum >= 1e9) {
    formatted = `$${(absNum / 1e9).toFixed(2)}B`;
  } else if (absNum >= 1e6) {
    formatted = `$${(absNum / 1e6).toFixed(3)}M`;
  } else if (absNum >= 1e3) {
    formatted = `$${(absNum / 1e3).toFixed(1)}K`;
  } else {
    formatted = `$${absNum.toFixed(2)}`;
  }
  
  return num < 0 ? `-${formatted}` : formatted;
};

export const formatCurrencyDelta = (value: string | number | undefined): string => {
  if (value === undefined || value === null) return '+$0.00';
  const num = typeof value === 'string' ? parseFloat(value) : value;
  if (isNaN(num)) return '+$0.00';
  
  const prefix = num > 0 ? '+' : '';
  return `${prefix}${formatCurrency(num)}`;
};

export const formatPercentage = (value: string | number | undefined): string => {
  if (value === undefined || value === null) return '0.00%';
  const num = typeof value === 'string' ? parseFloat(value) : value;
  if (isNaN(num)) return '0.00%';
  
  return `${num.toFixed(2)}%`;
};

export const formatPercentageDelta = (value: string | number | undefined): string => {
  if (value === undefined || value === null) return '+0.00%';
  const num = typeof value === 'string' ? parseFloat(value) : value;
  if (isNaN(num)) return '+0.00%';
  
  const prefix = num > 0 ? '+' : '';
  return `${prefix}${num.toFixed(2)}%`;
};

export const parseDecimal = (value: string | number | undefined): number => {
  if (value === undefined || value === null) return 0;
  return typeof value === 'string' ? parseFloat(value) : value;
};
