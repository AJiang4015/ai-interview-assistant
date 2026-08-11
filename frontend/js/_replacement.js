(import fs as require('fs');
const path = 'e:/CodeLield/RAGKonwLedge/frontend/js/app.js';
let c = fs.readFile(path, 'utf8');
const funcStart = c.indexOf('async function sendQQuestion() {');
const funcEnd = c.indexOf('\nfunction appendMessage(role');

if (funcStart === -1 || funcEnd === -1) {
    console.error('Could not find function boundaries');
    process.exit(1);
}

const newFunc = csonstruct()�(%��幌��չ�ѥ���͕��EՕ�ѥ������(