import React from 'react';
import { Link } from 'react-router-dom';
import { Leaf, Navigation, Camera, ShieldCheck } from 'lucide-react';

export default function Home() {
  return (
    <div className="home-container">
      <div className="hero text-center mb-8">
        <div className="flex justify-center mb-4">
          <Leaf size={64} className="text-accent" />
        </div>
        <h1 className="text-gradient" style={{ fontSize: '3rem', marginBottom: '1rem' }}>
          Pacha Cover
        </h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: '1.25rem', maxWidth: '600px', margin: '0 auto' }}>
          The smart urban forestry platform. Use AI to find the perfect tree for your neighborhood, plant it, and earn verified green credits.
        </p>
      </div>

      <div className="features" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '2rem', marginBottom: '3rem' }}>
        <div className="glass-panel text-center">
          <Navigation size={40} className="text-accent" style={{ margin: '0 auto 1rem auto' }} />
          <h3>AI Prescription</h3>
          <p style={{ color: 'var(--text-secondary)', marginTop: '0.5rem' }}>
            Get hyper-local tree recommendations based on your GPS and soil type using Gemini 2.5 Flash.
          </p>
        </div>

        <div className="glass-panel text-center">
          <Camera size={40} className="text-accent" style={{ margin: '0 auto 1rem auto' }} />
          <h3>Verify Growth</h3>
          <p style={{ color: 'var(--text-secondary)', marginTop: '0.5rem' }}>
            Upload a picture of your sapling. Our Vision AI verifies the plant instantly.
          </p>
        </div>

        <div className="glass-panel text-center">
          <ShieldCheck size={40} className="text-accent" style={{ margin: '0 auto 1rem auto' }} />
          <h3>Green Ledger</h3>
          <p style={{ color: 'var(--text-secondary)', marginTop: '0.5rem' }}>
            Your contributions are securely tracked and verified in the central ledger.
          </p>
        </div>
      </div>

      <div className="action-section text-center" style={{ maxWidth: '400px', margin: '0 auto' }}>
        <Link to="/heatmap" style={{ textDecoration: 'none' }}>
          <button className="btn-primary" style={{ padding: '1rem 2rem', fontSize: '1.25rem' }}>
            Start Planting Now
          </button>
        </Link>
      </div>
    </div>
  );
}
