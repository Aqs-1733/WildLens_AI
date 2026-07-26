from __future__ import annotations
import sys
import httpx

BASE="http://127.0.0.1:8010"

def main()->int:
    failures=0
    with httpx.Client(base_url=BASE,timeout=httpx.Timeout(20,connect=3),trust_env=False) as client:
        checks=[]
        try:
            login=client.post('/api/auth/login',json={'username':'explorer','password':'Wild1234!'})
            login.raise_for_status(); token=login.json()['access_token']; headers={'Authorization':f'Bearer {token}'}
            checks=[('健康检查','GET','/api/health',None,None),('首页数据','GET','/api/dashboard',None,headers),('物种百科','GET','/api/species',None,headers),('视频任务','GET','/api/videos/jobs',None,headers),('好友动态','GET','/api/social/feed',None,headers)]
        except Exception as exc:
            print(f'[FAIL] 登录: {exc}'); return 1
        for name,method,path,payload,request_headers in checks:
            try:
                response=client.request(method,path,json=payload,headers=request_headers)
                response.raise_for_status(); print(f'[PASS] {name}: HTTP {response.status_code}')
            except Exception as exc:
                failures+=1; print(f'[FAIL] {name}: {exc}')
    return 1 if failures else 0
if __name__=='__main__': sys.exit(main())
