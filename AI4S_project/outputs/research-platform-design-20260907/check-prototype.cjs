const fs = require('fs');
const path = require('path');
const assert = require('node:assert/strict');
const { chromium } = require('C:/Users/57806/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fragmentPath = 'C:/Users/57806/.codex/visualizations/2026/09/07/01a07aa0-2e84-7751-8a57-18532c64f041/research-decision-studio.html';
const fragment = fs.readFileSync(fragmentPath,'utf8');
assert(!fragment.includes('class=\\"'));
assert(!/<!doctype|<html|<body|<head>/i.test(fragment));
const errors=[];
const checks=[];
(async()=>{
 const browser = await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 const page=await browser.newPage({viewport:{width:1024,height:900},deviceScaleFactor:1});
 page.on('pageerror',e=>errors.push(e.message));
 await page.setContent('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><style>:root{color-scheme:light dark}body{margin:0}</style></head><body>'+fragment+'</body></html>');
 const goto=async p=>page.locator(`nav [data-page="${p}"]`).click();
 const click=async a=>page.locator(`[data-action="${a}"]`).first().click();
 const content=()=>page.locator('#rd-view').innerText();
 await goto('gaps');assert(await page.locator('[data-action="review-gap"]').isDisabled());
 await goto('search');await click('freeze');await page.locator('#rd-coverage').check();
 await goto('gaps');await click('review-gap');assert((await content()).includes('空白已模拟核查'));
 await click('pick');await click('submit');await page.locator('#rd-comment').fill('演示核查意见：需要限定适用条件。');await click('approve');
 assert((await content()).includes('模拟评审已核查'));checks.push('快照 → 覆盖检查 → 空白核查 → 选题 → 评审');
 await goto('home');await page.locator('[data-field="lab"]').selectOption('无');await click('constraints');
 await goto('gaps');assert((await content()).includes('当前条件下不建议开展：缺少实验条件'));
 await goto('proposal');assert((await content()).includes('需重新评审'));checks.push('资源约束改变可行性并使原评审待更新');
 await goto('evidence');await page.locator('[data-action="relation"][data-id="1"]').click();await page.locator('#rd-comparable').check();
 assert((await content()).includes('证据相互冲突'));assert((await content()).includes('证据不足 + 相互冲突'));checks.push('条件可比性控制冲突判断，多维证据状态并存');
 await goto('monitor');await click('save-monitor');await click('new-evidence');assert((await content()).includes('需重新核查'));
 await goto('gaps');assert(await page.locator('[data-action="review-gap"]').isDisabled());
 await goto('proposal');assert((await content()).includes('新增潜在反证'));checks.push('新反证撤回覆盖检查并保留历史版本');
 await goto('search');await page.locator('#rd-query').fill('ferroptosis AND radiotherapy');assert(await page.locator('#rd-coverage').isDisabled());
 await click('freeze');assert((await content()).includes('v2'));await page.locator('#rd-source-filter').selectOption('pat');assert.equal(await page.locator('.rd-record').count(),1);checks.push('检索修改生成新版本；来源筛选正确');
 await goto('proposal');await page.locator('#rd-draft').fill('草稿修订 <保留文字>');await goto('home');await goto('proposal');assert.equal(await page.locator('#rd-draft').inputValue(),'草稿修订 <保留文字>');checks.push('跨页保留草稿并正确转义文本');
 const pages=['home','direction','search','evidence','gaps','proposal','teams','monitor'];
 for(const theme of ['light','dark']){
   await page.emulateMedia({colorScheme:theme});
   for(const width of [1024,736,360]){
     await page.setViewportSize({width,height:900});
     for(const p of pages){
       await goto(p);
       const layout=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,width:innerWidth,escaped:[...document.querySelectorAll('#rd-studio button,#rd-studio input,#rd-studio select,#rd-studio textarea')].filter(e=>e.getClientRects().length&&e.getBoundingClientRect().right>innerWidth+1).map(e=>e.textContent)}));
       assert(layout.scroll<=layout.width+1,`${theme}/${width}/${p}: overflow ${JSON.stringify(layout)}`);
       assert.equal(layout.escaped.length,0,`${theme}/${width}/${p}: controls out of bounds`);
     }
   }
 }
 checks.push('八个页面在 1024/736/360 像素与浅色/深色下无横向溢出');
 await page.emulateMedia({colorScheme:'light'});await page.setViewportSize({width:1024,height:900});await goto('home');
 await page.screenshot({path:path.join(__dirname,'prototype-desktop.png'),fullPage:true});
 await goto('evidence');await page.screenshot({path:path.join(__dirname,'prototype-evidence.png'),fullPage:true});
 await page.emulateMedia({colorScheme:'dark'});await page.setViewportSize({width:360,height:900});await goto('gaps');await page.screenshot({path:path.join(__dirname,'prototype-mobile-dark.png'),fullPage:true});
 assert.equal(errors.length,0,errors.join('\n'));
 fs.writeFileSync(path.join(__dirname,'verification.json'),JSON.stringify({status:'passed',checks,runtimeErrors:errors,disclaimer:'原型状态验证，非真实研究或检索结果验证'},null,2));
 console.log(JSON.stringify({status:'passed',checks,runtimeErrors:errors},null,2));await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
