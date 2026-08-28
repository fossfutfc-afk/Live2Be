// spine-test.js — SpinePlayer 端到端验证: 真调后端 /api/spine + 前端播放器,
// 自动演示若干情绪切换; 状态写入 window.__spineTest 供无头验证读取。
import { SpinePlayer } from '/static/js/spine-player.js';

const stage = document.getElementById('stage');
const statusEl = document.getElementById('status');
const errEl = document.getElementById('err');
const controlsEl = document.getElementById('controls');
const setStatus = (t) => { statusEl.textContent = t; };

window.__spineTest = { phase: 'init' };

const player = new SpinePlayer();
window.__spineTest.player = player; // 逃生舱: 验证脚本可调底层

try {
  await player.mount(stage, { background: '#14181f' });
  setStatus('mount OK · 拉取 /api/spine/igusa_haruka …');

  const res = await fetch('/api/spine/igusa_haruka');
  if (!res.ok) throw new Error(`api ${res.status}: ${await res.text()}`);
  const meta = await res.json();
  window.__spineTest.meta = meta;

  setStatus(`pack=${meta.pack.name} · 加载资源…`);
  await player.load(meta.pack, { emotionMap: meta.emotions });

  window.__spineTest.info = {
    bones: player.bones,
    animations: player.animations,
    emotionCount: Object.keys(meta.emotions).length,
  };
  setStatus(`✓ 载入成功 · bones=${player.bones} · anims=${player.animations.length} · emotions=${window.__spineTest.info.emotionCount}`);

  // 控制面板: 动画按钮 + 情绪按钮
  for (const name of player.animations) {
    const b = document.createElement('button');
    b.textContent = name;
    b.onclick = () => { player.play(name, { loop: true }); setStatus(`▶ ${name}`); };
    controlsEl.appendChild(b);
  }
  for (const [emotion, anim] of Object.entries(meta.emotions)) {
    const b = document.createElement('button');
    b.className = 'emotion';
    b.textContent = `${emotion}→${anim}`;
    b.onclick = () => {
      const ok = player.setEmotion(emotion);
      setStatus(`setEmotion(${emotion}) → ${ok ? '播放 ' + player.currentAnimation : 'false(静默保持)'}`);
    };
    controlsEl.appendChild(b);
  }

  // 自动演示: 依次切情绪（每个停留 ~1.2s）
  const demo = ['nomal', 'smile', 'giggle', 'embarrass', 'shout', 'pensive'];
  for (const e of demo) {
    await new Promise((r) => setTimeout(r, 1200));
    const ok = player.setEmotion(e);
    window.__spineTest.lastEmotion = e;
    window.__spineTest.lastOk = ok;
    window.__spineTest.current = player.currentAnimation;
  }
  window.__spineTest.phase = 'demo-done';
  setStatus(`演示完成 · 当前动画: ${player.currentAnimation}`);
} catch (e) {
  console.error(e);
  window.__spineTest.phase = 'error';
  window.__spineTest.error = String((e && e.stack) || e);
  errEl.textContent = window.__spineTest.error;
  setStatus('❌ ' + (e && e.message));
}
