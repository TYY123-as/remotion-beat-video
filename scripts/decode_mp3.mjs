// 把 mp3 解码成单声道 float32 裸数据（.f32），供 analyze_beats.py 使用。
// 本机没有 ffmpeg，所以用纯 WASM 解码器 mpg123-decoder。
// 用法: node tools/decode_mp3.mjs [in.mp3] [out.f32]
import {readFileSync, writeFileSync} from 'node:fs';
import {MPEGDecoder} from 'mpg123-decoder';

const inp = process.argv[2] ?? 'public/music.mp3';
const out = process.argv[3] ?? 'public/music.f32';

const bytes = new Uint8Array(readFileSync(inp));
const dec = new MPEGDecoder();
await dec.ready; // WASM 初始化
const {channelData, samplesDecoded, sampleRate} = dec.decode(bytes);
dec.free();

const ch = channelData.length;
const n = samplesDecoded;
const mono = new Float32Array(n);
for (let i = 0; i < n; i++) {
  let s = 0;
  for (let c = 0; c < ch; c++) s += channelData[c][i];
  mono[i] = s / ch;
}
writeFileSync(out, Buffer.from(mono.buffer, mono.byteOffset, mono.byteLength));
// 采样率写进同名 sidecar，分析脚本据此读取
writeFileSync(`${out}.json`, JSON.stringify({sampleRate, channels: ch, samples: n, duration: +(n / sampleRate).toFixed(3)}, null, 1));
console.log(`解码完成: ${inp} -> ${out} | 声道 ${ch} | 采样率 ${sampleRate} | 时长 ${(n / sampleRate).toFixed(2)}s | 样本 ${n}`);
