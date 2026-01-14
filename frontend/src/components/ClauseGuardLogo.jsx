import React from 'react';

export const ClauseGuardLogo = ({ className = "w-8 h-8", variant = "dark" }) => {
  // Colors based on variant - dark for hero/dark backgrounds, light for white backgrounds
  const shieldColor = variant === "dark" ? "#5EEAD4" : "#0F766E";
  const scaleColor = variant === "dark" ? "#0F172A" : "#FFFFFF";
  
  return (
    <svg 
      viewBox="0 0 40 44" 
      fill="none" 
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      {/* Shield shape */}
      <path 
        d="M20 2L4 8V20C4 31.05 10.74 41.24 20 44C29.26 41.24 36 31.05 36 20V8L20 2Z" 
        fill={shieldColor}
      />
      {/* Scale/Balance */}
      <g transform="translate(8, 10)">
        {/* Center pole */}
        <rect x="11" y="4" width="2" height="18" fill={scaleColor} />
        {/* Top beam */}
        <rect x="4" y="4" width="16" height="2" fill={scaleColor} />
        {/* Left chain */}
        <rect x="5" y="6" width="1" height="6" fill={scaleColor} />
        {/* Right chain */}
        <rect x="18" y="6" width="1" height="6" fill={scaleColor} />
        {/* Left pan */}
        <path d="M2 12 L9 12 L8 16 L3 16 Z" fill={scaleColor} />
        {/* Right pan */}
        <path d="M15 12 L22 12 L21 16 L16 16 Z" fill={scaleColor} />
        {/* Base */}
        <rect x="8" y="22" width="8" height="2" fill={scaleColor} />
        {/* Base stand */}
        <path d="M10 22 L14 22 L13 24 L11 24 Z" fill={scaleColor} />
      </g>
    </svg>
  );
};

export default ClauseGuardLogo;
