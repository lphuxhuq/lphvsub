'use strict'

const fs = require('fs')
const path = require('path')

require('dotenv').config({ path: `${__dirname}/.env` })
const { MongoMemoryServer } = require('mongodb-memory-server')

async function start() {
  const dataDir = path.join(__dirname, 'data')
  fs.mkdirSync(dataDir, { recursive: true })

  console.log('[voxdub-dev] Đang khởi chạy MongoDB (lưu tại control_server/data)...')
  const mongod = await MongoMemoryServer.create({
    instance: {
      dbName: 'voxdub',
      dbPath: dataDir,
      storageEngine: 'wiredTiger',
    },
  })
  
  const uri = mongod.getUri()
  process.env.MONGODB_URI = uri
  console.log(`[voxdub-dev] MongoDB đã sẵn sàng tại: ${uri}`)

  // Seed default data & indexes
  try {
    const mongoose = require('mongoose')
    await mongoose.connect(uri)
    
    // Sync indexes
    const MODELS = [
      './src/models/Device',
      './src/models/ActivationKey',
      './src/models/CreditLedger',
      './src/models/CreditHold',
      './src/models/Order',
      './src/models/AiProvider',
      './src/models/AppConfig',
      './src/models/UsageLog',
      './src/models/AuditLog',
      './src/models/JobResult',
    ]
    for (const path of MODELS) {
      const Model = require(path)
      await Model.syncIndexes()
    }

    const AppConfig = require('./src/models/AppConfig')
    const { DEFAULTS } = require('./src/services/config.service')
    for (const [key, value] of Object.entries(DEFAULTS)) {
      await AppConfig.updateOne(
        { key },
        { $setOnInsert: { key, value } },
        { upsert: true }
      )
    }

    // Tự động nạp và cập nhật các API key từ .env
    const { syncProvidersFromEnv, providersFor } = require('./src/services/ai-gateway.service')
    await syncProvidersFromEnv()

    const activeList = await providersFor('translate')
    if (activeList.length) {
      const names = activeList.map(p => `${p.label || p.name} (${p.model})`).join(', ')
      console.log(`[voxdub-dev] Đã kích hoạt ${activeList.length} nơi dịch AI: ${names}`)
    } else {
      console.warn('[voxdub-dev] Chưa có API Key dịch AI nào — dịch tự động sẽ không hoạt động.')
      console.warn('[voxdub-dev] Hãy điền GEMINI_API_KEY hoặc OPENROUTER_API_KEY vào .env rồi khởi động lại app.')
      console.warn('[voxdub-dev] Hoặc thêm tại: http://localhost:3001/admin (Nơi gọi mô hình)')
    }

    console.log('[voxdub-dev] Đã nạp cấu hình ban đầu thành công!')
    await mongoose.connection.close()
  } catch (err) {
    console.warn('[voxdub-dev] Cảnh báo seed:', err.message)
  }

  // Boot server
  require('./server')
}

start().catch((err) => {
  console.error('[voxdub-dev] Lỗi khởi động:', err)
  process.exit(1)
})
