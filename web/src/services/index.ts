import { httpService } from './http'
import { mockService } from './mock'

export const dataMode = import.meta.env.VITE_DATA_MODE === 'http' ? 'http' : 'mock'
export const services = dataMode === 'http' ? httpService : mockService
