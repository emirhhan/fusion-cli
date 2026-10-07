const React = require('react');
exports.useCurrentFrame = () => 60;
exports.useVideoConfig = () => ({width:1920,height:1080,fps:30,durationInFrames:120});
exports.AbsoluteFill = React.forwardRef(({children,style},ref) => React.createElement('div',{ref,style:{position:'absolute',inset:0,display:'flex',...style}},children));

exports.useDelayRender = () => ({delayRender: () => 1, continueRender: () => {}, cancelRender: error => {throw error;}});
