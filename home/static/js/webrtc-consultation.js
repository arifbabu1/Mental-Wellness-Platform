/**
 * Enhanced WebRTC Consultation System
 */
class WebRTCConsultation {
    constructor(roomId, userId, userName, userRole) {
        this.roomId = roomId;
        this.userId = userId;
        this.userName = userName;
        this.userRole = userRole;
        
        // WebRTC configuration
        this.configuration = {
            iceServers: [
                { urls: 'stun:stun.l.google.com:19302' },
                { 
                    urls: 'turn:turn.example.com:3478',
                    username: 'user',
                    credential: 'pass'
                }
            ]
        };
        
        // WebRTC objects
        this.localStream = null;
        this.remoteStream = null;
        this.peerConnection = null;
        this.ws = null;
        
        // State
        this.isInitiator = false;
        this.isVideoOn = true;
        this.isAudioOn = true;
        this.isScreenSharing = false;
        this.isConnected = false;
        
        // Callbacks
        this.onRemoteStream = null;
        this.onConnectionStateChange = null;
        this.onChatMessage = null;
        this.onUserJoined = null;
        this.onUserLeft = null;
        
        this.init();
    }
    
    async init() {
        try {
            // Initialize WebSocket connection
            await this.initWebSocket();
            
            // Initialize local media
            await this.initLocalMedia();
            
            // Create peer connection
            await this.createPeerConnection();
            
            console.log('WebRTC consultation initialized successfully');
        } catch (error) {
            console.error('Failed to initialize WebRTC consultation:', error);
            this.updateStatus('Failed to initialize');
        }
    }
    
    async initWebSocket() {
        const wsUrl = `ws://localhost:8000/ws/consultation/${this.roomId}/`;
        this.ws = new WebSocket(wsUrl);
        
        this.ws.onopen = () => {
            console.log('WebSocket connected');
            this.updateStatus('Connected to signaling server');
        };
        
        this.ws.onmessage = async (event) => {
            const data = JSON.parse(event.data);
            await this.handleSignalingMessage(data);
        };
        
        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.updateStatus('Connection error');
        };
        
        this.ws.onclose = () => {
            console.log('WebSocket disconnected');
            this.updateStatus('Disconnected');
        };
    }
    
    async initLocalMedia() {
        try {
            // Get user media
            this.localStream = await navigator.mediaDevices.getUserMedia({
                video: {
                    width: { ideal: 1280 },
                    height: { ideal: 720 }
                },
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                }
            });
            
            // Display local video
            if (this.localVideo) {
                this.localVideo.srcObject = this.localStream;
            }
            
            console.log('Local media initialized');
        } catch (error) {
            console.error('Failed to get local media:', error);
            this.updateStatus('Failed to access camera/microphone');
            throw error;
        }
    }
    
    async createPeerConnection() {
        try {
            // Create RTCPeerConnection
            this.peerConnection = new RTCPeerConnection(this.configuration);
            
            // Add local stream
            this.localStream.getTracks().forEach(track => {
                this.peerConnection.addTrack(track, this.localStream);
            });
            
            // Handle ICE candidates
            this.peerConnection.onicecandidate = (event) => {
                if (event.candidate) {
                    this.sendSignalingMessage({
                        type: 'ice_candidate',
                        candidate: event.candidate
                    });
                }
            };
            
            // Handle remote stream
            this.peerConnection.ontrack = (event) => {
                if (event.streams && event.streams[0]) {
                    this.remoteStream = event.streams[0];
                    if (this.remoteVideo) {
                        this.remoteVideo.srcObject = this.remoteStream;
                    }
                    if (this.onRemoteStream) {
                        this.onRemoteStream(this.remoteStream);
                    }
                }
            };
            
            // Handle connection state changes
            this.peerConnection.onconnectionstatechange = () => {
                const state = this.peerConnection.connectionState;
                console.log('Connection state:', state);
                this.updateStatus(this.getConnectionStateText(state));
                this.isConnected = state === 'connected';
                
                if (this.onConnectionStateChange) {
                    this.onConnectionStateChange(state);
                }
            };
            
            console.log('Peer connection created');
        } catch (error) {
            console.error('Failed to create peer connection:', error);
            throw error;
        }
    }
    
    async createOffer() {
        try {
            this.isInitiator = true;
            const offer = await this.peerConnection.createOffer({
                offerToReceiveAudio: true,
                offerToReceiveVideo: true
            });
            
            await this.peerConnection.setLocalDescription(offer);
            this.sendSignalingMessage({
                type: 'offer',
                offer: offer
            });
            
            console.log('Offer created and sent');
        } catch (error) {
            console.error('Failed to create offer:', error);
            throw error;
        }
    }
    
    async handleOffer(data) {
        try {
            if (!this.isInitiator) {
                await this.peerConnection.setRemoteDescription(data.offer);
                const answer = await this.peerConnection.createAnswer();
                await this.peerConnection.setLocalDescription(answer);
                this.sendSignalingMessage({
                    type: 'answer',
                    answer: answer
                });
                console.log('Answer created and sent');
            }
        } catch (error) {
            console.error('Failed to handle offer:', error);
        }
    }
    
    async handleAnswer(data) {
        try {
            if (this.isInitiator) {
                await this.peerConnection.setRemoteDescription(data.answer);
                console.log('Answer received and set');
            }
        } catch (error) {
            console.error('Failed to handle answer:', error);
        }
    }
    
    async handleIceCandidate(data) {
        try {
            await this.peerConnection.addIceCandidate(data.candidate);
            console.log('ICE candidate added');
        } catch (error) {
            console.error('Failed to add ICE candidate:', error);
        }
    }
    
    async handleSignalingMessage(data) {
        switch (data.type) {
            case 'offer':
                await this.handleOffer(data);
                break;
            case 'answer':
                await this.handleAnswer(data);
                break;
            case 'ice_candidate':
                await this.handleIceCandidate(data);
                break;
            case 'chat_message':
                if (this.onChatMessage) {
                    this.onChatMessage(data);
                }
                break;
            case 'user_joined':
                if (this.onUserJoined) {
                    this.onUserJoined(data);
                }
                break;
            case 'user_left':
                if (this.onUserLeft) {
                    this.onUserLeft(data);
                }
                break;
        }
    }
    
    sendSignalingMessage(message) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(message));
        }
    }
    
    sendChatMessage(message) {
        this.sendSignalingMessage({
            type: 'chat_message',
            message: message
        });
    }
    
    toggleVideo() {
        this.isVideoOn = !this.isVideoOn;
        this.localStream.getVideoTracks().forEach(track => {
            track.enabled = this.isVideoOn;
        });
        return this.isVideoOn;
    }
    
    toggleAudio() {
        this.isAudioOn = !this.isAudioOn;
        this.localStream.getAudioTracks().forEach(track => {
            track.enabled = this.isAudioOn;
        });
        return this.isAudioOn;
    }
    
    async toggleScreenShare() {
        if (this.isScreenSharing) {
            // Stop screen sharing
            const videoTrack = this.localStream.getVideoTracks().find(
                track => track.label === 'screen'
            );
            if (videoTrack) {
                videoTrack.stop();
                this.localStream.removeTrack(videoTrack);
            }
            this.isScreenSharing = false;
        } else {
            // Start screen sharing
            try {
                const screenStream = await navigator.mediaDevices.getDisplayMedia({
                    video: true,
                    audio: false
                });
                
                const screenTrack = screenStream.getVideoTracks()[0];
                await this.peerConnection.addTrack(screenTrack, this.localStream);
                this.isScreenSharing = true;
                
                // Stop screen sharing when user ends it
                screenTrack.onended = () => {
                    this.toggleScreenShare();
                };
            } catch (error) {
                console.error('Failed to start screen sharing:', error);
            }
        }
        return this.isScreenSharing;
    }
    
    endCall() {
        // Close peer connection
        if (this.peerConnection) {
            this.peerConnection.close();
            this.peerConnection = null;
        }
        
        // Close WebSocket
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        
        // Stop local media
        if (this.localStream) {
            this.localStream.getTracks().forEach(track => track.stop());
            this.localStream = null;
        }
        
        this.isConnected = false;
        console.log('Call ended');
    }
    
    getConnectionStateText(state) {
        switch (state) {
            case 'new':
                return 'Connecting...';
            case 'connecting':
                return 'Connecting...';
            case 'connected':
                return 'Connected';
            case 'disconnected':
                return 'Disconnected';
            case 'failed':
                return 'Connection Failed';
            case 'closed':
                return 'Call Ended';
            default:
                return 'Unknown';
        }
    }
    
    updateStatus(message) {
        const statusElement = document.getElementById('connectionStatus');
        if (statusElement) {
            statusElement.textContent = message;
        }
    }
    
    setLocalVideo(videoElement) {
        this.localVideo = videoElement;
    }
    
    setRemoteVideo(videoElement) {
        this.remoteVideo = videoElement;
    }
}

// Export for use in templates
window.WebRTCConsultation = WebRTCConsultation;
