import { useState, type KeyboardEvent } from 'react';
import { useNavigate } from 'react-router-dom';

interface UseThreadGalleryInputResult {
  message: string;
  setMessage: React.Dispatch<React.SetStateAction<string>>;
  planMode: boolean;
  setPlanMode: React.Dispatch<React.SetStateAction<boolean>>;
  isLoading: boolean;
  handleSend: () => Promise<void>;
  handleKeyPress: (e: KeyboardEvent) => void;
}

export function useThreadGalleryInput(workspaceId: string): UseThreadGalleryInputResult {
  const [message, setMessage] = useState('');
  const [planMode, setPlanMode] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const navigate = useNavigate();

  const handleSend = async () => {
    if (!message.trim() || isLoading || !workspaceId) {
      return;
    }

    setIsLoading(true);
    try {
      navigate(`/chat/t/__default__`, {
        state: {
          workspaceId,
          initialMessage: message.trim(),
          planMode: planMode,
        },
      });

      setMessage('');
    } catch (error) {
      console.error('Error navigating to thread:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e: KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return {
    message,
    setMessage,
    planMode,
    setPlanMode,
    isLoading,
    handleSend,
    handleKeyPress,
  };
}
