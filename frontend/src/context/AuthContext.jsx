import React, { createContext, useContext, useState, useEffect } from 'react';
import { setAuthToken, setupInterceptors } from '../api/client';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(null);
    const [token, setToken] = useState(localStorage.getItem('token') || sessionStorage.getItem('token'));
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (token) {
            axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
            setAuthToken(token); // Update client.js instance as well
            // Optionally fetch user profile info here if you have an endpoint
            setUser({ email: 'user@example.com' }); // Placeholder or decode JWT
        } else {
            delete axios.defaults.headers.common['Authorization'];
            setAuthToken(null);
            setUser(null);
        }
        setLoading(false);
    }, [token]);

    // Setup Axios Interceptor for 401s (Global & Client)
    useEffect(() => {
        // 1. Global Axios
        const interceptor = axios.interceptors.response.use(
            (response) => response,
            (error) => {
                if (error.response && error.response.status === 401) {
                    logout();
                }
                return Promise.reject(error);
            }
        );

        // 2. Client.js Instance
        setupInterceptors(() => logout());

        return () => {
            axios.interceptors.response.eject(interceptor);
        };
    }, []);

    const login = async (email, password, remember = true) => {
        const formData = new FormData();
        formData.append('username', email);
        formData.append('password', password);

        try {
            const response = await axios.post('/api/v1/auth/token', formData);
            const { access_token } = response.data;

            if (remember) {
                localStorage.setItem('token', access_token);
                sessionStorage.removeItem('token');
            } else {
                sessionStorage.setItem('token', access_token);
                localStorage.removeItem('token');
            }

            setToken(access_token);
            return { success: true };
        } catch (error) {
            const message = error.response?.data?.detail || error.message || 'Login failed';
            return {
                success: false,
                message: message
            };
        }
    };

    const register = async (email, password) => {
        try {
            await axios.post('/api/v1/auth/register', { email, password });
            return await login(email, password, true); // Auto-login after register (default remember=true)
        } catch (error) {
            const message = error.response?.data?.detail || error.message || 'Registration failed';
            return {
                success: false,
                message: message
            };
        }
    }

    const logout = () => {
        localStorage.removeItem('token');
        sessionStorage.removeItem('token');
        setToken(null);
        setUser(null);
        window.location.href = '/login';
    };

    return (
        <AuthContext.Provider value={{ user, token, login, logout, register, loading }}>
            {!loading && children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => useContext(AuthContext);
