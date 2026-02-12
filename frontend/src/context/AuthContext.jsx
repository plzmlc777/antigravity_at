import React, { createContext, useContext, useState, useEffect } from 'react';
import { setAuthToken, setupInterceptors, resetRedirectFlag } from '../api/client';
import axios from 'axios';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(null);
    const [token, setToken] = useState(localStorage.getItem('token') || sessionStorage.getItem('token'));
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (token) {
            axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
            setAuthToken(token);

            const storedEmail = localStorage.getItem('user_email') || sessionStorage.getItem('user_email') || '';
            const storedIsAdmin = localStorage.getItem('is_admin') === 'true' || sessionStorage.getItem('is_admin') === 'true';
            setUser({ email: storedEmail, is_admin: storedIsAdmin });
        } else {
            delete axios.defaults.headers.common['Authorization'];
            setAuthToken(null);
            setUser(null);
        }
        setLoading(false);
    }, [token]);

    // Setup Axios Interceptor for 401s - auto logout on token expiration or session kick
    useEffect(() => {
        setupInterceptors((reason) => {
            localStorage.removeItem('token');
            localStorage.removeItem('is_admin');
            localStorage.removeItem('user_email');
            localStorage.removeItem('has_active_account');
            sessionStorage.removeItem('token');
            sessionStorage.removeItem('is_admin');
            sessionStorage.removeItem('user_email');
            sessionStorage.removeItem('has_active_account');
            if (reason === 'session_kicked') {
                sessionStorage.setItem('logout_reason', 'session_kicked');
            }
            window.location.href = '/login';
        });
    }, []);

    const login = async (email, password, remember = true) => {
        const formData = new FormData();
        formData.append('username', email);
        formData.append('password', password);

        try {
            const response = await axios.post('/api/v1/auth/token', formData);
            const { access_token, is_admin, has_active_account } = response.data;

            // Set axios headers IMMEDIATELY before any state updates
            // This prevents race condition where API calls happen before headers are set
            axios.defaults.headers.common['Authorization'] = `Bearer ${access_token}`;
            setAuthToken(access_token);

            if (remember) {
                localStorage.setItem('token', access_token);
                localStorage.setItem('is_admin', is_admin ? 'true' : 'false');
                localStorage.setItem('user_email', email);
                localStorage.setItem('has_active_account', has_active_account ? 'true' : 'false');
                sessionStorage.removeItem('token');
                sessionStorage.removeItem('is_admin');
                sessionStorage.removeItem('user_email');
                sessionStorage.removeItem('has_active_account');
            } else {
                sessionStorage.setItem('token', access_token);
                sessionStorage.setItem('is_admin', is_admin ? 'true' : 'false');
                sessionStorage.setItem('user_email', email);
                sessionStorage.setItem('has_active_account', has_active_account ? 'true' : 'false');
                localStorage.removeItem('token');
                localStorage.removeItem('is_admin');
                localStorage.removeItem('user_email');
                localStorage.removeItem('has_active_account');
            }

            resetRedirectFlag();
            setToken(access_token);
            setUser({ email, is_admin });
            return { success: true, has_active_account };
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
        localStorage.removeItem('is_admin');
        localStorage.removeItem('user_email');
        localStorage.removeItem('has_active_account');
        sessionStorage.removeItem('token');
        sessionStorage.removeItem('is_admin');
        sessionStorage.removeItem('user_email');
        sessionStorage.removeItem('has_active_account');
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
