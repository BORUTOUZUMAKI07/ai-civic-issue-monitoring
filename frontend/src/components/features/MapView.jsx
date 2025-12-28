import React, { useEffect, useState } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polygon } from 'react-leaflet';
import { Card } from '../ui/Card';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// Fix for default markers in React Leaflet
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
});

// Create a custom smaller icon for ward centers
const wardIcon = new L.Icon({
    iconUrl: 'https://cdn-icons-png.flaticon.com/512/1042/1042263.png',
    iconSize: [24, 24],
    iconAnchor: [12, 12],
});

// Vadodara Coordinates
const CENTER = [22.3072, 73.1812];

export const MapView = () => {
    const [wards, setWards] = useState({});
    const [issues, setIssues] = useState([
        { id: 1, lat: 22.3072, lng: 73.1812, type: 'Pothole', severity: 'High' },
        { id: 2, lat: 22.3150, lng: 73.2000, type: 'Garbage', severity: 'Medium' },
    ]);

    useEffect(() => {
        // Fetch real Ward data from Backend
        fetch('http://localhost:8000/wards')
            .then(res => res.json())
            .then(data => setWards(data))
            .catch(err => console.error("Could not load wards:", err));
    }, []);

  return (
    <div className="h-full w-full relative z-0">
        <MapContainer 
            center={CENTER} 
            zoom={13} 
            style={{ height: '100%', width: '100%' }}
            className="z-0"
        >
            <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
            />
            
            {/* Render Ward Boundaries (Polygons) */}
            {Object.entries(wards).map(([name, coords]) => (
                <React.Fragment key={name}>
                    <Polygon 
                        positions={coords} 
                        pathOptions={{ 
                            color: '#3b82f6', 
                            weight: 2, 
                            fillOpacity: 0.05,
                            dashArray: '5, 5'
                        }} 
                    />
                    {/* Mark the Center of each Ward */}
                    <Marker 
                        position={[
                            coords.reduce((sum, p) => sum + p[0], 0) / coords.length,
                            coords.reduce((sum, p) => sum + p[1], 0) / coords.length
                        ]}
                        icon={wardIcon}
                    >
                        <Popup>
                            <div className="text-center">
                                <p className="font-bold text-blue-600">{name}</p>
                                <p className="text-xs text-gray-500 uppercase">Assigned Ward</p>
                            </div>
                        </Popup>
                    </Marker>
                </React.Fragment>
            ))}

            {/* Render Issues */}
            {issues.map(issue => (
                <Marker key={issue.id} position={[issue.lat, issue.lng]}>
                    <Popup>
                        <div className="font-sans">
                            <strong className="block text-sm">{issue.type}</strong>
                            <span className="text-xs text-gray-600">Severity: {issue.severity}</span>
                        </div>
                    </Popup>
                </Marker>
            ))}
        </MapContainer>
        
        {/* Overlay Badge */}
        <div className="absolute top-4 right-4 z-[400] bg-white/90 backdrop-blur px-3 py-1 rounded-full border border-blue-200 text-xs font-bold text-blue-700 shadow-md">
            VMC ADMIN VIEW: 19 WARDS ACTIVE
        </div>
    </div>
  );
};
