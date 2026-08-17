'use strict'

const mongoose = require('mongoose')
const Device = require('./src/models/Device')
const AppConfig = require('./src/models/AppConfig')

async function run() {
  // Discover running mongodb memory server port if connected or localhost
  const uri = process.env.MONGODB_URI || 'mongodb://localhost:27017/voxdub'
  console.log('Connecting to:', uri)
  await mongoose.connect(uri)

  const res = await Device.updateMany({}, { $set: { balance: 10000000 } })
  console.log('Updated devices balance:', res)

  await AppConfig.updateOne({ key: 'trial.vox' }, { $set: { value: 10000000 } }, { upsert: true })
  await AppConfig.updateOne({ key: 'trial.upfront.vox' }, { $set: { value: 10000000 } }, { upsert: true })
  console.log('Updated config trial.vox to 10,000,000')

  await mongoose.disconnect()
}

run().catch(console.error)
