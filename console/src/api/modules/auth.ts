import { getApiUrl } from "../config";

export interface LoginResponse {
  token: string;
  username: string;
  message?: string;
}

export interface AuthStatusResponse {
  enabled: boolean;
  has_users: boolean;
}

export interface VerifyResponse {
  valid: boolean;
  username: string;
  user_id: string;
  is_admin: boolean;
}

export interface UserRecord {
  user_id: string;
  username: string;
  is_admin: boolean;
}

export const authApi = {
  login: async (username: string, password: string): Promise<LoginResponse> => {
    const res = await fetch(getApiUrl("/auth/login"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Login failed");
    }
    return res.json();
  },

  register: async (
    username: string,
    password: string,
  ): Promise<LoginResponse> => {
    const res = await fetch(getApiUrl("/auth/register"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Registration failed");
    }
    return res.json();
  },

  getStatus: async (): Promise<AuthStatusResponse> => {
    const res = await fetch(getApiUrl("/auth/status"));
    if (!res.ok) throw new Error("Failed to check auth status");
    return res.json();
  },

  verify: async (): Promise<VerifyResponse> => {
    const token = localStorage.getItem("qwenpaw_auth_token") || "";
    const res = await fetch(getApiUrl("/auth/verify"), {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error("Token invalid");
    return res.json();
  },

  updateProfile: async (
    currentPassword: string,
    newUsername?: string,
    newPassword?: string,
  ): Promise<LoginResponse> => {
    const token = localStorage.getItem("qwenpaw_auth_token") || "";
    const res = await fetch(getApiUrl("/auth/update-profile"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        current_password: currentPassword,
        new_username: newUsername || null,
        new_password: newPassword || null,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Update failed");
    }
    return res.json();
  },

  listUsers: async (): Promise<UserRecord[]> => {
    const token = localStorage.getItem("qwenpaw_auth_token") || "";
    const res = await fetch(getApiUrl("/auth/users"), {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to load users");
    }
    return res.json();
  },

  createUser: async (username: string, password: string): Promise<UserRecord> => {
    const token = localStorage.getItem("qwenpaw_auth_token") || "";
    const res = await fetch(getApiUrl("/auth/users"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to create user");
    }
    return res.json();
  },

  resetUserPassword: async (userId: string, newPassword: string): Promise<void> => {
    const token = localStorage.getItem("qwenpaw_auth_token") || "";
    const res = await fetch(getApiUrl(`/auth/users/${encodeURIComponent(userId)}/password`), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ new_password: newPassword }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to reset password");
    }
  },

  deleteUser: async (userId: string): Promise<void> => {
    const token = localStorage.getItem("qwenpaw_auth_token") || "";
    const res = await fetch(getApiUrl(`/auth/users/${encodeURIComponent(userId)}`), {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to delete user");
    }
  },
};
