import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { X, Plus, Rocket, ChevronRight, Target, FileText } from 'lucide-react';

/**
 * NewProfileModal - Create a new strategy profile
 *
 * Step 1: Select strategy
 * Step 2: Enter profile name and description
 * Step 3: Initialize with default Rank 1 config
 */
const NewProfileModal = ({ isOpen, onClose, onProfileCreated, strategies = [] }) => {
    const [step, setStep] = useState(1);
    const [selectedStrategyId, setSelectedStrategyId] = useState('');
    const [profileName, setProfileName] = useState('');
    const [profileDescription, setProfileDescription] = useState('');
    const [isCreating, setIsCreating] = useState(false);
    const [error, setError] = useState(null);

    // Reset state when modal opens/closes
    useEffect(() => {
        if (isOpen) {
            setStep(1);
            setSelectedStrategyId('');
            setProfileName('');
            setProfileDescription('');
            setError(null);
        }
    }, [isOpen]);

    const selectedStrategy = strategies.find(s => s.id === selectedStrategyId);

    const handleNext = () => {
        if (step === 1 && selectedStrategyId) {
            setStep(2);
        }
    };

    const handleBack = () => {
        if (step === 2) {
            setStep(1);
        }
    };

    const handleCreate = async () => {
        if (!profileName.trim()) {
            setError('프로필 이름을 입력해주세요');
            return;
        }

        setIsCreating(true);
        setError(null);

        try {
            // Create profile with default Rank 1 config
            // The actual rank config will be initialized by the parent component
            onProfileCreated({
                strategyId: selectedStrategyId,
                strategyName: selectedStrategy?.name || selectedStrategyId,
                name: profileName.trim(),
                description: profileDescription.trim()
            });

            onClose();
        } catch (err) {
            console.error('Failed to create profile:', err);
            setError(err.message || '프로필 생성에 실패했습니다');
        } finally {
            setIsCreating(false);
        }
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-gradient-to-b from-gray-900 to-gray-950 border border-white/10 rounded-2xl w-full max-w-lg shadow-2xl">
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-white/10">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-emerald-500/20 flex items-center justify-center">
                            <Plus size={20} className="text-emerald-400" />
                        </div>
                        <div>
                            <h2 className="text-lg font-bold text-white">New Profile</h2>
                            <p className="text-xs text-gray-500">Step {step} of 2</p>
                        </div>
                    </div>
                    <button
                        onClick={onClose}
                        className="p-2 hover:bg-white/5 rounded-lg transition-colors"
                    >
                        <X size={20} className="text-gray-400" />
                    </button>
                </div>

                {/* Progress Bar */}
                <div className="px-6 pt-4">
                    <div className="flex items-center gap-2">
                        <div className={`flex-1 h-1 rounded-full ${step >= 1 ? 'bg-emerald-500' : 'bg-white/10'}`} />
                        <div className={`flex-1 h-1 rounded-full ${step >= 2 ? 'bg-emerald-500' : 'bg-white/10'}`} />
                    </div>
                </div>

                {/* Content */}
                <div className="p-6">
                    {step === 1 && (
                        <div className="space-y-4">
                            <div className="flex items-center gap-2 text-gray-300 mb-4">
                                <Target size={18} className="text-blue-400" />
                                <span className="font-medium">전략 선택</span>
                            </div>

                            <p className="text-sm text-gray-500 mb-4">
                                이 프로필에서 사용할 트레이딩 전략을 선택하세요.
                            </p>

                            <div className="space-y-2 max-h-64 overflow-y-auto">
                                {strategies.map(strategy => (
                                    <button
                                        key={strategy.id}
                                        onClick={() => setSelectedStrategyId(strategy.id)}
                                        className={`w-full p-4 rounded-xl border text-left transition-all ${
                                            selectedStrategyId === strategy.id
                                                ? 'bg-emerald-500/10 border-emerald-500/50 shadow-lg shadow-emerald-500/10'
                                                : 'bg-white/5 border-white/10 hover:border-white/20'
                                        }`}
                                    >
                                        <div className="flex items-center gap-3">
                                            <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                                                selectedStrategyId === strategy.id
                                                    ? 'bg-emerald-500/20'
                                                    : 'bg-white/5'
                                            }`}>
                                                <Rocket size={18} className={
                                                    selectedStrategyId === strategy.id
                                                        ? 'text-emerald-400'
                                                        : 'text-gray-500'
                                                } />
                                            </div>
                                            <div className="flex-1 min-w-0">
                                                <div className="font-medium text-white truncate">
                                                    {strategy.name}
                                                </div>
                                                <div className="text-xs text-gray-500 truncate">
                                                    {strategy.description || strategy.id}
                                                </div>
                                            </div>
                                            {selectedStrategyId === strategy.id && (
                                                <div className="text-emerald-400 text-lg">✓</div>
                                            )}
                                        </div>
                                    </button>
                                ))}
                            </div>

                            {strategies.length === 0 && (
                                <div className="text-center py-8 text-gray-500">
                                    <Rocket size={32} className="mx-auto mb-2 opacity-50" />
                                    <p>사용 가능한 전략이 없습니다</p>
                                </div>
                            )}
                        </div>
                    )}

                    {step === 2 && (
                        <div className="space-y-4">
                            <div className="flex items-center gap-2 text-gray-300 mb-4">
                                <FileText size={18} className="text-purple-400" />
                                <span className="font-medium">프로필 정보</span>
                            </div>

                            {/* Selected Strategy Info */}
                            <div className="p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-lg mb-4">
                                <div className="flex items-center gap-2">
                                    <Rocket size={14} className="text-emerald-400" />
                                    <span className="text-sm text-emerald-300">전략: {selectedStrategy?.name}</span>
                                </div>
                            </div>

                            <div>
                                <label className="block text-sm text-gray-400 mb-2">
                                    프로필 이름 <span className="text-red-400">*</span>
                                </label>
                                <input
                                    type="text"
                                    value={profileName}
                                    onChange={(e) => setProfileName(e.target.value)}
                                    placeholder="예: 삼성전자 단타 전략"
                                    className="w-full bg-black/40 border border-white/10 rounded-lg px-4 py-3 text-white placeholder-gray-600 outline-none focus:border-emerald-500/50"
                                    autoFocus
                                />
                            </div>

                            <div>
                                <label className="block text-sm text-gray-400 mb-2">
                                    설명 (선택사항)
                                </label>
                                <textarea
                                    value={profileDescription}
                                    onChange={(e) => setProfileDescription(e.target.value)}
                                    placeholder="이 프로필에 대한 메모..."
                                    rows={3}
                                    className="w-full bg-black/40 border border-white/10 rounded-lg px-4 py-3 text-white placeholder-gray-600 outline-none focus:border-emerald-500/50 resize-none"
                                />
                            </div>

                            {error && (
                                <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
                                    {error}
                                </div>
                            )}
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="px-6 py-4 border-t border-white/10 flex items-center justify-between">
                    {step === 1 ? (
                        <>
                            <button
                                onClick={onClose}
                                className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
                            >
                                취소
                            </button>
                            <button
                                onClick={handleNext}
                                disabled={!selectedStrategyId}
                                className="px-6 py-2.5 bg-gradient-to-r from-emerald-600 to-emerald-500 hover:from-emerald-500 hover:to-emerald-400 text-white font-bold rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                            >
                                다음
                                <ChevronRight size={16} />
                            </button>
                        </>
                    ) : (
                        <>
                            <button
                                onClick={handleBack}
                                className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
                            >
                                ← 이전
                            </button>
                            <button
                                onClick={handleCreate}
                                disabled={isCreating || !profileName.trim()}
                                className="px-6 py-2.5 bg-gradient-to-r from-emerald-600 to-emerald-500 hover:from-emerald-500 hover:to-emerald-400 text-white font-bold rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                            >
                                {isCreating ? (
                                    <>
                                        <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                        생성 중...
                                    </>
                                ) : (
                                    <>
                                        <Plus size={16} />
                                        프로필 생성
                                    </>
                                )}
                            </button>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
};

export default NewProfileModal;
