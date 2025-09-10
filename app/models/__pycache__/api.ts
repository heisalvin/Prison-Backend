import axios from "axios"
import type {
  User,
  AuthResponse,
  InmateOut,
  CreateInmateRequest,
  UpdateInmateRequest,
  RecognitionResult,
  LogsResponse,
} from "@/types"

const API_BASE_URL = "http://localhost:8000"

// Create axios instance
const api = axios.create({
  baseURL: API_BASE_URL,
})

// Add token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token")
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Auth services
export const authService = {
  async login(email: string, password: string): Promise<AuthResponse> {
    const formData = new FormData()
    formData.append("username", email)
    formData.append("password", password)

    const response = await api.post("/auth/login", formData, {
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
    })
    return response.data
  },

  async register(name: string, email: string, password: string): Promise<User> {
    const response = await api.post("/auth/register", {
      name,
      email,
      password,
    })
    return response.data
  },
}

// Inmates services
export const inmatesService = {
  async getInmates(): Promise<InmateOut[]> {
    const response = await api.get("/inmates/")
    return response.data
  },

  async getInmate(id: string): Promise<InmateOut> {
    const response = await api.get(`/inmates/${id}`)
    return response.data
  },

  async createInmate(data: CreateInmateRequest): Promise<InmateOut> {
    const formData = new FormData()
    formData.append("inmate_id", data.inmate_id)
    formData.append("name", data.name)

    // Append flat extra info fields
    if (data.extra_info?.cell) {
      formData.append("cell", data.extra_info.cell)
    }
    if (data.extra_info?.crime) {
      formData.append("crime", data.extra_info.crime)
    }
    if (data.extra_info?.sentence) {
      formData.append("sentence", data.extra_info.sentence)
    }

    // Append images
    data.images.forEach((image) => {
      formData.append("images", image)
    })

    const response = await api.post("/inmates/", formData, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    })
    return response.data
  },

  async updateInmate(id: string, data: UpdateInmateRequest): Promise<InmateOut> {
    const formData = new FormData()
    if (data.name) formData.append("name", data.name)
    if (data.extra_info?.cell) formData.append("cell", data.extra_info.cell)
    if (data.extra_info?.crime) formData.append("crime", data.extra_info.crime)
    if (data.extra_info?.sentence) formData.append("sentence", data.extra_info.sentence)

    const response = await api.patch(`/inmates/${id}`, formData, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    })

    return response.data
  },

  async deleteInmate(inmateid: string): Promise<void> {
    await api.delete(`/inmates/by-inmate-id${inmateid}`)
  },
}

// Recognition services
export const recognitionService = {
  async recognizeImage(image: File): Promise<RecognitionResult> {
    const formData = new FormData()
    formData.append("image", image)

    const response = await api.post("/recognize/", formData, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    })
    return response.data
  },
}

// Logs services
export const logsService = {
  async getDailyRecognitions(days = 7): Promise<LogsResponse> {
    const response = await api.get(`/logs/recognitions-daily?days=${days}`)
    return response.data
  },

  async getTopInmates(days = 30): Promise<LogsResponse> {
    const response = await api.get(`/logs/top-inmates?days=${days}`)
    return response.data
  },

  async getRecognitionsByOfficer(): Promise<LogsResponse> {
    const response = await api.get("/logs/recognitions-by-officer")
    return response.data
  },
}
