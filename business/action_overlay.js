// A presentation-only shadow overlay. No form writes, event cancellation or requests.
({label, kind, box, motion = true}) => {
  const id = 'guduu-action-cue';
  let host = document.getElementById(id);
  if (!host) {
    host = document.createElement('div'); host.id = id;
    host.setAttribute('aria-hidden', 'true'); host.setAttribute('role', 'presentation');
    Object.assign(host.style, {position:'fixed', inset:'0', zIndex:'2147483647', pointerEvents:'none', contain:'layout style', opacity:'1'});
    host.attachShadow({mode:'open'}); document.documentElement.appendChild(host);
  }
  clearTimeout(host._fadeTimer); clearTimeout(host._removeTimer);
  host.getAnimations().forEach(animation=>animation.cancel());
  host.style.opacity = '1';
  const root = host.shadowRoot; root.replaceChildren();
  const animate = motion && !matchMedia('(prefers-reduced-motion: reduce)').matches;
  const create = (tag, styles, text) => {
    const element = document.createElement(tag); Object.assign(element.style, styles);
    if (text) element.textContent = text;
    root.appendChild(element); return element;
  };
  const ripple = (x,y) => {
    const ring=create('div',{position:'fixed',left:(x-16)+'px',top:(y-16)+'px',width:'32px',height:'32px',
      border:'2px solid #527cc4',borderRadius:'50%',background:'#6a98e72b',boxSizing:'border-box'});
    ring.dataset.effect='click-ripple';
    if (animate) ring.animate([{transform:'scale(.3)',opacity:1},{transform:'scale(2.1)',opacity:0}],
      {duration:600,easing:'ease-out'}).finished.then(()=>ring.remove()).catch(()=>ring.remove());
    else setTimeout(()=>ring.remove(),400);
  };
  host.dataset.kind = kind; host.dataset.label = label;
  const chip = create('div', {position:'fixed', top:'18px', left:'50%', transform:'translateX(-50%)',
    maxWidth:'min(580px, 80vw)', padding:'10px 16px', borderRadius:'12px', border:'1px solid #cad6e9',
    background:'rgba(255,255,255,.97)', boxShadow:'0 6px 28px #18254120', color:'#182541',
    font:'600 13px "Microsoft YaHei UI", sans-serif', whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis'},
    'GuDuu OS  ·  ' + label);
  if (animate) chip.animate([{opacity:0, marginTop:'-6px'}, {opacity:1, marginTop:'0'}], {duration:200,easing:'ease-out'});
  if (box) {
    const frame = create('div', {position:'fixed', left:(box.x-5)+'px', top:(box.y-5)+'px',
      width:(box.width+10)+'px', height:(box.height+10)+'px', boxSizing:'border-box', border:'2px solid #577fc2',
      borderRadius:'8px', background:'#638ce212', boxShadow:'0 0 0 5px #6c95e117'});
    const x = (Math.max(0,box.x)+Math.min(innerWidth,box.x+box.width))/2;
    const y = (Math.max(0,box.y)+Math.min(innerHeight,box.y+box.height))/2;
    const cursor = create('div', {position:'fixed', top:'0',left:'0', width:'24px',height:'28px',
      filter:'drop-shadow(0 2px 3px #18254144)',transform:`translate(${x}px,${y}px)`});
    cursor.innerHTML = '<svg width="24" height="28" viewBox="0 0 24 28"><path d="M3 2L20 15L12 16L8 24Z" fill="#182541" stroke="white" stroke-width="2" stroke-linejoin="round"/></svg>';
    if (animate && kind==='target') cursor.animate([
      {transform:`translate(${host._x ?? 40}px,${host._y ?? 90}px)`},
      {transform:`translate(${x}px,${y}px)`}
    ],{duration:260,easing:'cubic-bezier(.22,.61,.36,1)'});
    host._x=x; host._y=y;
    if (animate && kind==='target') frame.animate([{opacity:.3},{opacity:1}],{duration:300});
    if (kind==='target') {
      delete host.dataset.clicked;
      host._expectedClick = true;
      if (!host._listening) {
        host._listening = true;
        document.addEventListener('click', event => {
          if (!event.isTrusted || !host.isConnected || !host._expectedClick) return;
          host._expectedClick = false; host.dataset.clicked = 'true';
          host._clickX=event.clientX;host._clickY=event.clientY;
          ripple(event.clientX,event.clientY);
        },{capture:true,passive:true});
      }
    }
  }
  if (kind==='complete' && host.dataset.clicked==='true' && Number.isFinite(host._clickX)) ripple(host._clickX,host._clickY);
  if (kind!=='target') host._expectedClick=false;
  host._fadeTimer = setTimeout(()=>{
    if (animate) host.animate([{opacity:1},{opacity:0}],{duration:250,fill:'forwards'});
    else host.style.opacity='0';
    host._removeTimer=setTimeout(()=>{root.replaceChildren();host.style.opacity='0';},300);
  },kind==='target'?2500:1500);
  return {kind, label, highlighted:!!box};
}
