const express = require('express');
const cors = require('cors');
const jwt = require('jsonwebtoken');

const app = express();
app.use(cors());
app.use(express.json());

const JWT_SECRET = 'RoboVLA-JWT-Secret';

// ========== 模拟数据 ==========
const devices = [
  { id:1, hardwareSn:'JET-2025-A001', deviceName:'深圳工厂 1号线 视觉定位站', authType:'perpetual', status:'online', totalProduction:45218, faultCount:2, lastHeartbeat:'2025-07-12 14:52:31' },
  { id:2, hardwareSn:'JET-2025-A002', deviceName:'深圳工厂 2号线 码垛拣选站', authType:'annual', status:'online', totalProduction:31890, faultCount:5, lastHeartbeat:'2025-07-12 14:51:18' },
  { id:3, hardwareSn:'JET-2025-A003', deviceName:'苏州工厂 3号线 螺丝锁付站', authType:'perpetual', status:'online', totalProduction:56234, faultCount:0, lastHeartbeat:'2025-07-12 14:53:02' },
  { id:4, hardwareSn:'JET-2025-B004', deviceName:'苏州工厂 1号线 物流搬运站', authType:'trial', status:'offline', totalProduction:1200, faultCount:3, lastHeartbeat:'2025-07-10 09:15:44' },
  { id:5, hardwareSn:'JET-2025-B005', deviceName:'东莞工厂 2号线 打磨抛光站', authType:'rental', status:'online', totalProduction:28450, faultCount:1, lastHeartbeat:'2025-07-12 14:50:55' },
  { id:6, hardwareSn:'JET-2025-C006', deviceName:'东莞工厂 5号线 视觉检测站', authType:'annual', status:'offline', totalProduction:0, faultCount:0, lastHeartbeat:'--' },
];

// ========== JWT 鉴权中间件 ==========
const auth = (req, res, next) => {
  const header = req.headers.authorization;
  if (!header || !header.startsWith('Bearer ')) {
    return res.status(401).json({ code:401, msg:'未授权' });
  }
  try {
    jwt.verify(header.slice(7), JWT_SECRET);
    next();
  } catch(e) {
    return res.status(401).json({ code:401, msg:'Token 已过期' });
  }
};

// DEMO 模式：自动签发 token（跳过登录页）
app.get('/api/auth/token', (req, res) => {
  const token = jwt.sign({ userId:1, role:'ADMIN' }, JWT_SECRET, { expiresIn:'24h' });
  res.json({ code:0, data:{ token, user:{ id:1, username:'admin', role:'ADMIN', realName:'系统管理员' } }, msg:'ok' });
});

app.post('/api/auth/login', (req, res) => {
  const { username, password } = req.body || {};
  if (username === 'admin' && password === 'admin123') {
    const token = jwt.sign({ userId:1, role:'ADMIN' }, JWT_SECRET, { expiresIn:'8h' });
    return res.json({ code:0, data:{ token, user:{ id:1, username:'admin', role:'ADMIN', realName:'系统管理员' } }, msg:'ok' });
  }
  res.status(401).json({ code:401, msg:'用户名或密码错误' });
});

// ========== 业务接口 (DEMO模式放行所有请求) ==========
const demoAuth = (req, res, next) => {
  // 演示模式：有 token 就验证，没有也放行
  const header = req.headers.authorization;
  if (header && header.startsWith('Bearer ')) {
    try {
      jwt.verify(header.slice(7), JWT_SECRET);
    } catch(e) {
      // demo 模式下忽略无效 token
    }
  }
  next();
};

// 设备集群概览
app.get('/api/device/cluster', demoAuth, (req, res) => {
  const online = devices.filter(d => d.status === 'online').length;
  const total = devices.length;
  const totalProduction = devices.reduce((s, d) => s + d.totalProduction, 0);
  res.json({
    code:0,
    data: {
      onlineDevices: online,
      totalDevices: total,
      totalProduction,
      onlineRate: total > 0 ? Math.round(online / total * 1000) / 10 : 0,
      devices,
    },
    msg:'ok'
  });
});

// 设备列表
app.get('/api/device/list', demoAuth, (req, res) => {
  res.json({ code:0, data:devices, msg:'ok' });
});

// 日报表
app.get('/api/report/daily', demoAuth, (req, res) => {
  const date = req.query.date || '2025-07-12';
  const day = new Date(date).getDate();
  const base = 1000 + day * 50 + Math.floor(Math.random() * 200);
  const good = base - Math.floor(Math.random() * 60);
  const bad = base - good;
  res.json({
    code:0,
    data: {
      date,
      totalCycles: base,
      goodCount: good,
      badCount: bad,
      yieldRate: Math.round(good / base * 1000) / 10,
      durationHours: (18 + Math.random() * 6).toFixed(1),
      errors: Math.floor(Math.random() * 5),
      trend: {
        hours: ['08:00','10:00','12:00','14:00','16:00','18:00','20:00'],
        good: [120,180,150,210,195,230,97],
        bad: [8,12,5,15,9,11,5],
      },
      defectReasons: [
        { reason:'定位偏差', count:23 },
        { reason:'抓取超时', count:18 },
        { reason:'来料异常', count:12 },
        { reason:'视觉误判', count:8 },
        { reason:'气缸未到位', count:4 },
      ],
      details: [
        { time:'08:15', cycle:'001', sku:'A-2025-X1', status:'良品', duration:'12s' },
        { time:'08:18', cycle:'002', sku:'A-2025-X1', status:'良品', duration:'11s' },
        { time:'08:22', cycle:'003', sku:'A-2025-X1', status:'不良', duration:'14s' },
        { time:'08:26', cycle:'004', sku:'A-2025-X2', status:'良品', duration:'10s' },
        { time:'08:30', cycle:'005', sku:'A-2025-X2', status:'良品', duration:'11s' },
        { time:'08:34', cycle:'006', sku:'A-2025-X1', status:'良品', duration:'12s' },
        { time:'08:38', cycle:'007', sku:'A-2025-X3', status:'不良', duration:'15s' },
        { time:'08:42', cycle:'008', sku:'A-2025-X3', status:'良品', duration:'13s' },
      ],
    },
    msg:'ok'
  });
});

// 月报表
app.get('/api/report/monthly', demoAuth, (req, res) => {
  res.json({
    code:0,
    data: {
      month: '2025-07',
      totalCycles: 31245,
      goodCount: 29870,
      badCount: 1375,
      yieldRate: 95.6,
    },
    msg:'ok'
  });
});

// 设备注册 (授权)
app.post('/api/device/register', demoAuth, (req, res) => {
  const { hardwareSn, authType } = req.body || {};
  const code = Array.from({ length: 32 }, () =>
    'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'[Math.floor(Math.random() * 36)]
  ).join('');
  res.json({
    code:0,
    data: { hardware_sn: hardwareSn, license_code: code, auth_type: authType || 'trial' },
    msg:'ok'
  });
});

// 导出 Excel
app.get('/api/report/export', demoAuth, (req, res) => {
  res.setHeader('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
  res.setHeader('Content-Disposition', 'attachment; filename=report.xlsx');
  res.send(Buffer.from('demo-excel'));
});

// 健康检查
app.get('/api/health', (req, res) => {
  res.json({ status:'UP', version:'2.0.0-mock' });
});

// 启动
const PORT = process.env.PORT || 8080;
app.listen(PORT, () => {
  console.log(`✅ RoboVLA Mock API 已启动: http://localhost:${PORT}`);
  console.log(`   登录: POST /api/auth/login  { username:"admin", password:"admin123" }`);
  console.log(`   设备: GET  /api/device/cluster`);
  console.log(`   报表: GET  /api/report/daily?date=2025-07-12`);
});
