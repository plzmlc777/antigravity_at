import React, { createContext, useContext, useState, useEffect } from 'react';
import axios from 'axios';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(null);
    const [token, setToken] = useState(localStorage.getItem('token'));
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (token) {
            axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
            // Optionally fetch user profile info here if you have an endpoint
            setUser({ email: 'user@example.com' }); // Placeholder or decode JWT
        } else {
            delete axios.defaults.headers.common['Authorization'];
            setUser(null);
        }
        setLoading(false);
    }, [token]);

    const login = async (email, password) => {
        const formData = new FormData();
        formData.append('username', email);
        formData.append('password', password);

        try {
            const response = await axios.post('/api/v1/auth/token', formData);
            const { access_token } = response.data;
            localStorage.setItem('token', access_token);
            setToken(access_token);
            return { success: true };
        } catch (error) {
            return {
                success: false,
                message: error.response?.data?.detail || 'Login failed'
            };
        }
    };

    const register = async (email, password) => {
        try {
            await axios.post('/api/v1/auth/register', { email, password });
            return await login(email, password);
        } catch (error) {
            const message = error.response?.data?.detail || error.message || 'Registration failed';
            const register = async (email, password) => {
                try {
                    await axios.post('/api/v1/auth/register', { email, password });
                    return await login(email, password, true);
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
